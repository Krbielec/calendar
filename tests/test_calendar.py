import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.database import Database
from app.recurrence import due_dates


class CalendarDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db = Database(Path(self.temp_dir.name) / "calendar.sqlite3")
        self.db.initialize()

    def test_retrieves_sample_events_for_week(self) -> None:
        # These sample bills are due Friday, 28 February 2025.
        monthly_id = self.db.create_event("Netflix", date(2025, 1, 31), 1)
        quarterly_id = self.db.create_event("Electricity", date(2024, 11, 28), 3)
        one_time_id = self.db.create_event("Annual insurance", date(2025, 2, 28), 0)
        self.db.create_event("Spotify", date(2025, 1, 31), 2)
        self.db.create_event("Car insurance", date(2025, 2, 1), 12)

        events = self.db.events_for_week(date(2025, 2, 24))

        self.assertEqual(
            [(event["title"], event["date"]) for event in events],
            [
                ("Annual insurance", "2025-02-28"),
                ("Electricity", "2025-02-28"),
                ("Netflix", "2025-02-28"),
            ],
        )
        self.assertTrue(all(not event["paid"] for event in events))
        self.assertEqual({event["id"] for event in events}, {monthly_id, quarterly_id, one_time_id})

    def test_paid_status_applies_to_one_occurrence(self) -> None:
        netflix_id = self.db.create_event("Netflix", date(2025, 1, 31), 1)
        february_due = date(2025, 2, 24)

        self.db.set_paid(netflix_id, date(2025, 2, 28), True)
        events = self.db.events_for_week(february_due)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["paid"])

        self.db.set_paid(netflix_id, date(2025, 2, 28), False)
        events = self.db.events_for_week(february_due)
        self.assertFalse(events[0]["paid"])

        march_events = self.db.events_for_week(date(2025, 3, 31))
        self.assertEqual(len(march_events), 1)
        self.assertFalse(march_events[0]["paid"])


class RecurrenceTests(unittest.TestCase):
    def test_month_end_fallback_returns_to_anchor_day(self) -> None:
        self.assertEqual(
            due_dates(date(2024, 1, 31), 1, date(2024, 2, 1), date(2024, 4, 30)),
            [date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)],
        )

    def test_multi_month_intervals_stay_anchored(self) -> None:
        self.assertEqual(
            due_dates(date(2025, 1, 31), 2, date(2025, 1, 1), date(2025, 8, 31)),
            [date(2025, 1, 31), date(2025, 3, 31), date(2025, 5, 31), date(2025, 7, 31)],
        )


if __name__ == "__main__":
    unittest.main()
