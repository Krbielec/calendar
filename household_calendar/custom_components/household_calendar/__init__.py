"""Home Assistant services for the Household Calendar add-on."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.typing import ConfigType

DOMAIN = "household_calendar"
WEEK_REQUEST_EVENT = "household_calendar_week_requested"
WEEK_RESPONSE_EVENT = "household_calendar_week_response"
PAID_EVENT = "household_calendar_paid"
SERVICE_GET_WEEK = "get_week"
SERVICE_SET_PAID = "set_paid"
RESPONSE_TIMEOUT = 30
LOG = logging.getLogger(__name__)


def _monday(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise ServiceValidationError("monday must be an ISO date") from err
    if parsed.weekday() != 0:
        raise ServiceValidationError("monday must be the Monday of the requested week")
    return parsed


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register response-returning services usable by non-admin dashboard users."""
    pending: dict[str, asyncio.Future[ServiceResponse]] = {}

    def handle_response(event: Event) -> None:
        request_id = event.data.get("request_id")
        future = pending.get(request_id)
        if future is None or future.done():
            return
        future.set_result({
            "monday": event.data.get("monday"),
            "events": event.data.get("events", []),
        })

    hass.bus.async_listen(WEEK_RESPONSE_EVENT, handle_response)

    async def request_addon(
        call: ServiceCall, event_type: str, event_data: dict[str, Any]
    ) -> ServiceResponse:
        request_id = uuid4().hex
        future: asyncio.Future[ServiceResponse] = hass.loop.create_future()
        pending[request_id] = future
        hass.bus.async_fire(
            event_type,
            {**event_data, "request_id": request_id},
            context=call.context,
        )
        try:
            return await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)
        except TimeoutError as err:
            LOG.warning("Timed out waiting for add-on response to %s", event_type)
            raise HomeAssistantError(
                "Household Calendar add-on did not respond. Check that it is running."
            ) from err
        finally:
            pending.pop(request_id, None)

    async def get_week(call: ServiceCall) -> ServiceResponse:
        monday = _monday(call.data["monday"])
        return await request_addon(
            call,
            WEEK_REQUEST_EVENT,
            {"monday": monday.isoformat()},
        )

    async def set_paid(call: ServiceCall) -> ServiceResponse:
        monday = _monday(call.data["monday"])
        try:
            due_date = date.fromisoformat(call.data["due_date"])
        except (TypeError, ValueError) as err:
            raise ServiceValidationError("due_date must be an ISO date") from err
        if (due_date - monday).days not in range(7):
            raise ServiceValidationError("due_date must belong to the requested week")
        return await request_addon(
            call,
            PAID_EVENT,
            {
                "event_id": call.data["event_id"],
                "due_date": due_date.isoformat(),
                "paid": call.data["paid"],
                "monday": monday.isoformat(),
            },
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_WEEK,
        get_week,
        schema=vol.Schema({vol.Required("monday"): str}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PAID,
        set_paid,
        schema=vol.Schema({
            vol.Required("event_id"): vol.All(int, vol.Range(min=1)),
            vol.Required("due_date"): str,
            vol.Required("paid"): bool,
            vol.Required("monday"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    return True
