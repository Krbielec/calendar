"""Small Ingress-only web interface for managing recurring event definitions."""

from datetime import date
import logging

from aiohttp import web

from .database import Database
from .home_assistant import HomeAssistantBridge

LOG = logging.getLogger("household_calendar.admin")
INGRESS_PROXY_IP = "172.30.32.2"
ADMIN_HTML = "/app/www/admin.html"


@web.middleware
async def ingress_only(request: web.Request, handler):
    # Home Assistant's Ingress proxy is the only supported entry point. This
    # prevents the unauthenticated CRUD API being exposed to the add-on network.
    if request.remote != INGRESS_PROXY_IP:
        raise web.HTTPForbidden(text="Use the Home Assistant sidebar to access this page.")
    return await handler(request)


def _event_payload(body: object) -> tuple[str, date, int]:
    if not isinstance(body, dict):
        raise ValueError("Expected a JSON object")
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Enter an event name")
    try:
        due_date = date.fromisoformat(body.get("first_due_date", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid first due date") from exc
    interval = body.get("interval_months")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise ValueError("Choose a recurrence")
    if interval not in (0, 1, 2, 3, 12):
        raise ValueError("Choose a supported recurrence")
    return title, due_date, interval


def create_app(db: Database, bridge: HomeAssistantBridge) -> web.Application:
    app = web.Application(middlewares=[ingress_only], client_max_size=16 * 1024)

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(ADMIN_HTML)

    async def list_events(_request: web.Request) -> web.Response:
        return web.json_response(db.list_events())

    async def create_event(request: web.Request) -> web.Response:
        try:
            title, due_date, interval = _event_payload(await request.json())
            event_id = db.create_event(title, due_date, interval)
        except (ValueError, web.HTTPBadRequest) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        await _refresh(bridge)
        return web.json_response({"id": event_id}, status=201)

    async def update_event(request: web.Request) -> web.Response:
        event_id = _event_id(request)
        try:
            title, due_date, interval = _event_payload(await request.json())
            db.update_event(event_id, title, due_date, interval)
        except (ValueError, web.HTTPBadRequest) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        await _refresh(bridge)
        return web.json_response({"ok": True})

    async def archive_event(request: web.Request) -> web.Response:
        event_id = _event_id(request)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("active"), bool):
                raise ValueError("Expected active to be true or false")
            db.set_event_active(event_id, body["active"])
        except (ValueError, web.HTTPBadRequest) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        await _refresh(bridge)
        return web.json_response({"ok": True})

    app.router.add_get("/", index)
    app.router.add_get("/api/events", list_events)
    app.router.add_post("/api/events", create_event)
    app.router.add_put("/api/events/{event_id}", update_event)
    app.router.add_patch("/api/events/{event_id}/active", archive_event)
    return app


def _event_id(request: web.Request) -> int:
    try:
        event_id = int(request.match_info["event_id"])
        if event_id < 1:
            raise ValueError
        return event_id
    except ValueError as exc:
        raise web.HTTPBadRequest(text="Invalid event id") from exc


async def _refresh(bridge: HomeAssistantBridge) -> None:
    if bridge.active_monday is not None:
        try:
            await bridge.publish_week(bridge.active_monday)
        except Exception:
            LOG.exception("Event was saved, but the calendar sensor could not be refreshed")


async def run_admin_server(db: Database, bridge: HomeAssistantBridge, stopped) -> None:
    runner = web.AppRunner(create_app(db, bridge), access_log=LOG)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8099)
    await site.start()
    LOG.info("Admin page listening for Home Assistant Ingress on port 8099")
    try:
        await stopped.wait()
    finally:
        await runner.cleanup()
