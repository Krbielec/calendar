# Household Calendar

A Home Assistant add-on for a weekly, day-grouped calendar of household events such as bills.

## Initial design

- The Lovelace card will show Monday through Sunday and navigate between weeks.
- Events are stored locally in SQLite under `/data`, so they survive add-on restarts.
- Recurrences are anchored to the first due date. Supported intervals are one month, two months, three months, and twelve months. If an anchor day does not exist in a month, that occurrence uses the month's final day; later occurrences return to the anchor day.
- Paid state belongs to an individual occurrence. Marking one occurrence paid leaves later occurrences unpaid.
- Recurring event definitions are managed in the add-on's Ingress panel; paid state belongs to individual dated occurrences.

## Lovelace card

The add-on copies and registers its card automatically. It also installs the `household_calendar` Home Assistant integration under `/config/custom_components`. On first install of version 0.4.0 or later, add this top-level entry to `configuration.yaml` (merge it with any existing keys) and restart Home Assistant once to load the integration:

```yaml
household_calendar:
```

Then add a manual card to a dashboard with:

```yaml
type: custom:household-calendar-card
```

The add-on publishes the current week as `sensor.household_calendar_week`. The card uses the integration's `get_week` and `set_paid` response services, so authenticated non-admin users can navigate independently and mark occurrences paid. The integration relays requests to the add-on and returns the matching response to each caller; paid-state changes are written to the local SQLite database.

## Manage events

Open the add-on's **Household Calendar** sidebar panel (or its **Open Web UI** button) to create, edit, archive, and restore event definitions. Recurrence supports one-time, monthly, every two months, quarterly, and annual schedules. Editing a definition changes the generated schedule while retaining paid occurrence records; archiving pauses future display without deleting history.

## Test without Home Assistant

Run the database and recurrence tests with `python -m unittest discover -v`. To preview the card with browser-only mock events, run `python -m http.server 8000` from this directory and open `http://localhost:8000/dev/preview.html`. The preview exercises week navigation and paid toggles; those mock changes are not written to SQLite.

## Add-on development

The app repository manifest is `repository.yaml`; the add-on itself is in `household_calendar/`. Home Assistant provides its Supervisor token, options file, and persistent `/data` directory. Run locally with Home Assistant's app build tooling; the container is not intended to run without Supervisor credentials.
