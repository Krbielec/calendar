"""Home Assistant REST and WebSocket bridge for the Lovelace card."""

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from .database import Database

LOG = logging.getLogger("household_calendar.ha")
ENTITY_ID = "sensor.household_calendar_week"
WEEK_REQUEST_EVENT = "household_calendar_week_requested"
WEEK_RESPONSE_EVENT = "household_calendar_week_response"
PAID_EVENT = "household_calendar_paid"


class HomeAssistantBridge:
    def __init__(self, db: Database, timezone: str, version: str) -> None:
        self.db = db
        self.timezone = timezone
        self.version = version
        self.token = os.environ["SUPERVISOR_TOKEN"]
        self.api_url = "http://supervisor/core/api"
        self.websocket_url = "ws://supervisor/core/websocket"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.active_monday: date | None = None

    @staticmethod
    def monday_for(day: date) -> date:
        return day - timedelta(days=day.weekday())

    async def publish_week(self, day: date) -> None:
        monday = self.monday_for(day)
        self.active_monday = monday
        events = self.db.events_for_week(monday)
        attrs = {
            "friendly_name": "Household Calendar",
            "monday": monday.isoformat(),
            "sunday": (monday + timedelta(days=6)).isoformat(),
            "events": events,
            "updated_at": datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds"),
            "timezone": self.timezone,
        }
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            response = await client.post(f"{self.api_url}/states/{ENTITY_ID}", json={"state": len(events), "attributes": attrs})
            response.raise_for_status()
        LOG.info("Published %d events for week starting %s", len(events), monday)

    async def _send(self, socket: Any, command_id: int, command: dict[str, Any]) -> dict[str, Any]:
        await socket.send(json.dumps({"id": command_id, **command}))
        while True:
            response = json.loads(await socket.recv())
            if response.get("id") == command_id:
                if not response.get("success", False):
                    raise RuntimeError(f"Home Assistant command failed: {response.get('error')}")
                return response

    async def _register_card(self, socket: Any) -> None:
        result = await self._send(socket, 1, {"type": "lovelace/resources"})
        resource_url = f"/local/household_calendar/household-calendar-card.js?v={self.version}"
        resources = result.get("result") or []
        existing = next((item for item in resources if item.get("url", "").split("?", 1)[0] == resource_url.split("?", 1)[0]), None)
        if existing:
            if existing.get("url") != resource_url:
                await self._send(socket, 2, {
                    "type": "lovelace/resources/update",
                    "resource_id": existing["id"],
                    "url": resource_url,
                })
        else:
            await self._send(socket, 2, {
                "type": "lovelace/resources/create",
                "res_type": "module",
                "url": resource_url,
            })

    async def run(self, stopped: asyncio.Event) -> None:
        while not stopped.is_set():
            try:
                async with websockets.connect(self.websocket_url, ping_interval=20, ping_timeout=20) as socket:
                    greeting = json.loads(await socket.recv())
                    if greeting.get("type") != "auth_required":
                        raise RuntimeError("Unexpected Home Assistant WebSocket greeting")
                    await socket.send(json.dumps({"type": "auth", "access_token": self.token}))
                    auth = json.loads(await socket.recv())
                    if auth.get("type") != "auth_ok":
                        raise RuntimeError(f"Home Assistant authentication failed: {auth}")

                    try:
                        await self._register_card(socket)
                    except Exception as exc:
                        LOG.warning("Could not register the Lovelace card automatically: %s", exc)
                    await self._send(socket, 3, {"type": "subscribe_events", "event_type": WEEK_REQUEST_EVENT})
                    await self._send(socket, 4, {"type": "subscribe_events", "event_type": PAID_EVENT})
                    LOG.info("Home Assistant WebSocket connected; card registered and commands subscribed")

                    while not stopped.is_set():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1)
                        except asyncio.TimeoutError:
                            continue
                        message = json.loads(raw)
                        if message.get("type") != "event":
                            continue
                        event = message.get("event", {})
                        await self._handle_event(event.get("event_type", ""), event.get("data", {}))
            except (OSError, ConnectionClosed, RuntimeError, ValueError, httpx.HTTPError) as exc:
                if not stopped.is_set():
                    LOG.warning("Home Assistant connection failed: %s; retrying in 10 seconds", exc)
                    try:
                        await asyncio.wait_for(stopped.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        pass

    async def _handle_event(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == WEEK_REQUEST_EVENT:
            try:
                requested = date.fromisoformat(str(data["monday"]))
                if requested.weekday() != 0:
                    raise ValueError("requested date is not a Monday")
                request_id = self._request_id(data)
            except (KeyError, TypeError, ValueError) as exc:
                LOG.warning("Ignoring invalid week request: %s", exc)
                return
            await self.publish_week(requested)
            await self._respond_with_week(requested, request_id)
        elif event_type == PAID_EVENT:
            try:
                if isinstance(data["event_id"], bool):
                    raise ValueError("event_id must be an integer")
                event_id = int(data["event_id"])
                due_date = date.fromisoformat(str(data["due_date"]))
                paid = data["paid"]
                if not isinstance(paid, bool):
                    raise ValueError("paid must be a boolean")
                request_id = self._request_id(data)
                requested = date.fromisoformat(str(data["monday"]))
                if requested.weekday() != 0:
                    raise ValueError("requested date is not a Monday")
                self.db.set_paid(event_id, due_date, paid)
            except (KeyError, TypeError, ValueError) as exc:
                LOG.warning("Ignoring invalid paid-state request: %s", exc)
                return
            await self.publish_week(requested)
            await self._respond_with_week(requested, request_id)

    @staticmethod
    def _request_id(data: dict[str, Any]) -> str:
        request_id = data["request_id"]
        if not isinstance(request_id, str) or not request_id or len(request_id) > 100:
            raise ValueError("request_id must be a non-empty string of at most 100 characters")
        return request_id

    async def _respond_with_week(self, monday: date, request_id: str) -> None:
        events = self.db.events_for_week(monday)
        payload = {
            "request_id": request_id,
            "monday": monday.isoformat(),
            "events": events,
        }
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            response = await client.post(
                f"{self.api_url}/events/{WEEK_RESPONSE_EVENT}",
                json=payload,
            )
            response.raise_for_status()
        LOG.info("Sent week response for %s (request %s)", monday, request_id)
