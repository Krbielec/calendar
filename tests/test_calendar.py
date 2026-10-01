import tempfile
import unittest
from datetime import date
from pathlib import Path

from household_calendar.app.database import Database
from household_calendar.app.recurrence import due_dates


class CalendarDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db = Database(Path(self.temp_dir.name) / "calendar.sqlite3")
        self.db.initialize()

    def test_database_starts_without_sample_events(self) -> None:
        self.assertEqual(self.db.list_events(), [])

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

    def test_one_time_event_does_not_recur(self) -> None:
        self.db.create_event("One-time repair", date(2025, 3, 5), 0)

        self.assertEqual(self.db.events_for_week(date(2025, 3, 3))[0]["title"], "One-time repair")
        self.assertEqual(self.db.events_for_week(date(2025, 4, 7)), [])

    def test_paid_state_rejects_date_outside_event_schedule(self) -> None:
        netflix_id = self.db.create_event("Netflix", date(2025, 1, 31), 1)

        with self.assertRaises(ValueError):
            self.db.set_paid(netflix_id, date(2025, 3, 30), True)

    def test_edit_changes_schedule_and_keeps_paid_occurrence_history(self) -> None:
        event_id = self.db.create_event("Netflix", date(2025, 1, 31), 1)
        self.db.set_paid(event_id, date(2025, 2, 28), True)

        self.db.update_event(event_id, "Streaming", date(2025, 3, 31), 2)

        self.assertEqual(
            self.db.events_for_week(date(2025, 3, 31)),
            [{"id": event_id, "title": "Streaming", "date": "2025-03-31", "paid": False}],
        )
        event = self.db.list_events()[0]
        self.assertEqual(event["paid_occurrences"], 1)
        self.assertEqual(event["first_due_date"], "2025-03-31")
        self.assertEqual(event["interval_months"], 2)

    def test_archiving_hides_future_events_and_restoring_keeps_history(self) -> None:
        event_id = self.db.create_event("Electricity", date(2025, 2, 28), 1)
        self.db.set_paid(event_id, date(2025, 2, 28), True)

        self.db.set_event_active(event_id, False)
        self.assertEqual(self.db.events_for_week(date(2025, 2, 24)), [])
        self.db.set_event_active(event_id, True)

        self.assertEqual(self.db.events_for_week(date(2025, 2, 24))[0]["paid"], True)
        self.assertEqual(self.db.list_events()[0]["paid_occurrences"], 1)

    def test_update_rejects_invalid_event_data(self) -> None:
        event_id = self.db.create_event("Netflix", date(2025, 1, 31), 1)

        with self.assertRaises(ValueError):
            self.db.update_event(event_id, "  ", date(2025, 2, 1), 1)
        with self.assertRaises(ValueError):
            self.db.update_event(event_id, "Netflix", date(2025, 2, 1), 4)

    def test_admin_list_reports_one_time_events_without_recurrence(self) -> None:
        self.db.create_event("Appointment", date(2025, 2, 1), 0)

        self.assertEqual(self.db.list_events()[0]["interval_months"], 0)


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
