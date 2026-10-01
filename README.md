# Household Calendar

A Home Assistant add-on for a weekly, day-grouped calendar of household events such as bills.

## Initial design

- The Lovelace card will show Monday through Sunday and navigate between weeks.
- Events are stored locally in SQLite under `/data`, so they survive add-on restarts.
- Recurrences are anchored to the first due date. Supported intervals are one month, two months, three months, and twelve months. If an anchor day does not exist in a month, that occurrence uses the month's final day; later occurrences return to the anchor day.
- Paid state belongs to an individual occurrence. Marking one occurrence paid leaves later occurrences unpaid.
- Event entry and editing are a later step. The initial database separates recurring event definitions from dated occurrences so that entry methods can be added without changing the calendar model.
- On first startup only, an empty event database is seeded with one unpaid, one-time Netflix event due tomorrow in the configured timezone. Existing databases with events are left alone.

## Lovelace card

The add-on copies and registers its card automatically. Add a manual card to a dashboard with:

```yaml
type: custom:household-calendar-card
```

The add-on publishes the displayed week as `sensor.household_calendar_week`. The card asks the add-on for other weeks and sends paid-state changes over Home Assistant's authenticated WebSocket event bus. The add-on writes each paid-state change to the local SQLite database and republishes that week.

## Test without Home Assistant

Run the database and recurrence tests with `python -m unittest discover -v`. To preview the card with browser-only mock events, run `python -m http.server 8000` from this directory and open `http://localhost:8000/dev/preview.html`. The preview exercises week navigation and paid toggles; those mock changes are not written to SQLite.

## Add-on development

The app repository manifest is `repository.yaml`; the add-on itself is in `household_calendar/`. Home Assistant provides its Supervisor token, options file, and persistent `/data` directory. Run locally with Home Assistant's app build tooling; the container is not intended to run without Supervisor credentials.
