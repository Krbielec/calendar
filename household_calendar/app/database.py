"""Local SQLite storage for recurring bill definitions and their occurrences."""

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from .recurrence import due_dates


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a connection and always release its file handle."""
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recurring_events (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    first_due_date TEXT NOT NULL,
                    frequency TEXT NOT NULL CHECK (frequency IN ('once', 'monthly', 'yearly')),
                    interval_months INTEGER NOT NULL DEFAULT 1 CHECK (interval_months > 0),
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS occurrences (
                    id INTEGER PRIMARY KEY,
                    event_id INTEGER NOT NULL REFERENCES recurring_events(id) ON DELETE CASCADE,
                    due_date TEXT NOT NULL,
                    paid_at TEXT,
                    UNIQUE (event_id, due_date)
                );

                CREATE INDEX IF NOT EXISTS idx_occurrences_due_date
                    ON occurrences(due_date);
                """
            )

    def create_event(self, title: str, first_due_date: date, interval_months: int) -> int:
        if not title.strip():
            raise ValueError("Event title cannot be empty")
        if interval_months not in (0, 1, 2, 3, 12):
            raise ValueError("Recurrence must be once, monthly, every 2 months, quarterly, or yearly")
        frequency = "once" if interval_months == 0 else ("yearly" if interval_months == 12 else "monthly")
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO recurring_events (title, first_due_date, frequency, interval_months) "
                "VALUES (?, ?, ?, ?)",
                (title.strip(), first_due_date.isoformat(), frequency, max(interval_months, 1)),
            )
            return int(cur.lastrowid)

    def ensure_initial_event(self, title: str, due_date: date) -> int | None:
        """Seed a one-time event only when there are no event definitions yet."""
        if not title.strip():
            raise ValueError("Event title cannot be empty")
        with self.session() as conn:
            existing = conn.execute("SELECT 1 FROM recurring_events LIMIT 1").fetchone()
            if existing:
                return None
            cur = conn.execute(
                "INSERT INTO recurring_events (title, first_due_date, frequency, interval_months) "
                "VALUES (?, ?, 'once', 1)",
                (title.strip(), due_date.isoformat()),
            )
            return int(cur.lastrowid)

    def events_for_week(self, monday: date) -> list[dict]:
        """Return that week's events, creating unpaid occurrence rows as needed."""
        sunday = date.fromordinal(monday.toordinal() + 6)
        with self.session() as conn:
            definitions = conn.execute(
                "SELECT id, title, first_due_date, frequency, interval_months "
                "FROM recurring_events WHERE active = 1"
            ).fetchall()
            result: list[dict] = []
            for event in definitions:
                dates = due_dates(
                    date.fromisoformat(event["first_due_date"]),
                    0 if event["frequency"] == "once" else event["interval_months"],
                    monday,
                    sunday,
                )
                for due in dates:
                    conn.execute(
                        "INSERT OR IGNORE INTO occurrences (event_id, due_date) VALUES (?, ?)",
                        (event["id"], due.isoformat()),
                    )
                    row = conn.execute(
                        "SELECT paid_at FROM occurrences WHERE event_id = ? AND due_date = ?",
                        (event["id"], due.isoformat()),
                    ).fetchone()
                    result.append({
                        "id": event["id"],
                        "title": event["title"],
                        "date": due.isoformat(),
                        "paid": row["paid_at"] is not None,
                    })
            return sorted(result, key=lambda item: (item["date"], item["title"].casefold()))

    def set_paid(self, event_id: int, due_date: date, paid: bool) -> None:
        """Set paid state for one occurrence only."""
        with self.session() as conn:
            definition = conn.execute(
                "SELECT first_due_date, frequency, interval_months "
                "FROM recurring_events WHERE id = ? AND active = 1",
                (event_id,),
            ).fetchone()
            if definition is None:
                raise ValueError("Event does not exist or is inactive")
            interval = 0 if definition["frequency"] == "once" else definition["interval_months"]
            if not due_dates(
                date.fromisoformat(definition["first_due_date"]), interval, due_date, due_date
            ):
                raise ValueError("Date is not an occurrence of this event")
            conn.execute(
                "INSERT OR IGNORE INTO occurrences (event_id, due_date) VALUES (?, ?)",
                (event_id, due_date.isoformat()),
            )
            conn.execute(
                "UPDATE occurrences SET paid_at = "
                "CASE WHEN ? THEN COALESCE(paid_at, CURRENT_TIMESTAMP) ELSE NULL END "
                "WHERE event_id = ? AND due_date = ?",
                (int(paid), event_id, due_date.isoformat()),
            )
