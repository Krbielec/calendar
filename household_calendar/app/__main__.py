"""Home Assistant add-on entry point."""

import asyncio
import json
import logging
import os
import shutil
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .admin import run_admin_server
from .database import Database
from .home_assistant import HomeAssistantBridge

LOG = logging.getLogger("household_calendar")
OPTIONS_PATH = Path("/data/options.json")
DATABASE_PATH = Path("/data/calendar.sqlite3")
CARD_SOURCE = Path("/app/www/household-calendar-card.js")
CARD_DESTINATION = Path("/config/www/household_calendar/household-calendar-card.js")
INTEGRATION_SOURCE = Path("/app/custom_components/household_calendar")
INTEGRATION_DESTINATION = Path("/config/custom_components/household_calendar")
ADDON_VERSION = "0.4.0"


async def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    if not OPTIONS_PATH.exists():
        raise RuntimeError("Add-on options file is missing at /data/options.json")
    if not os.getenv("SUPERVISOR_TOKEN"):
        raise RuntimeError("SUPERVISOR_TOKEN is missing; run this inside Home Assistant")

    options = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    db = Database(DATABASE_PATH)
    db.initialize()
    LOG.info("Database ready; configured timezone: %s", options["timezone"])
    CARD_DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    CARD_DESTINATION.write_bytes(CARD_SOURCE.read_bytes())
    shutil.copytree(INTEGRATION_SOURCE, INTEGRATION_DESTINATION, dirs_exist_ok=True)
    LOG.info("Installed Household Calendar Home Assistant integration files")

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)

    bridge = HomeAssistantBridge(db, options["timezone"], ADDON_VERSION)

    async def publish_initial_week() -> None:
        delay = 5
        while not stopped.is_set():
            try:
                await bridge.publish_week(datetime.now(ZoneInfo(options["timezone"])).date())
                return
            except httpx.HTTPError as exc:
                LOG.warning("Home Assistant API is not ready: %s; retrying in %d seconds", exc, delay)
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    delay = min(delay * 2, 60)

    await asyncio.gather(
        publish_initial_week(),
        bridge.run(stopped),
        run_admin_server(db, bridge, stopped),
    )


if __name__ == "__main__":
    asyncio.run(run())
