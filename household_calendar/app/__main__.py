"""Home Assistant add-on entry point."""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .admin import run_admin_server
from .database import Database
from .home_assistant import HomeAssistantBridge

LOG = logging.getLogger("household_calendar")
OPTIONS_PATH = Path("/data/options.json")
DATABASE_PATH = Path("/data/calendar.sqlite3")
CARD_SOURCE = Path("/app/www/household-calendar-card.js")
CARD_DESTINATION = Path("/config/www/household_calendar/household-calendar-card.js")
ADDON_VERSION = "0.3.0"


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

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)

    bridge = HomeAssistantBridge(db, options["timezone"], ADDON_VERSION)
    await bridge.publish_week(datetime.now(ZoneInfo(options["timezone"])).date())
    await asyncio.gather(bridge.run(stopped), run_admin_server(db, bridge, stopped))


if __name__ == "__main__":
    asyncio.run(run())
