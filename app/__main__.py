"""Home Assistant add-on entry point."""

import asyncio
import json
import logging
import os
import signal
from pathlib import Path

from .database import Database

LOG = logging.getLogger("household_calendar")
OPTIONS_PATH = Path("/data/options.json")
DATABASE_PATH = Path("/data/calendar.sqlite3")


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

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    await stopped.wait()


if __name__ == "__main__":
    asyncio.run(run())
