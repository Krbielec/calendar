# Household Calendar

A Home Assistant add-on for a weekly, day-grouped calendar of household events such as bills.

## Initial design

- The Lovelace card will show Monday through Sunday and navigate between weeks.
- Events are stored locally in SQLite under `/data`, so they survive add-on restarts.
- Recurrences are anchored to the first due date. Supported intervals are one month, two months, three months, and twelve months. If an anchor day does not exist in a month, that occurrence uses the month's final day; later occurrences return to the anchor day.
- Paid state belongs to an individual occurrence. Marking one occurrence paid leaves later occurrences unpaid.
- Event entry and editing are a later step. The initial database separates recurring event definitions from dated occurrences so that entry methods can be added without changing the calendar model.

## Add-on development

The add-on manifest is `config.yaml`. Home Assistant provides its Supervisor token, options file, and persistent `/data` directory. Run locally with Home Assistant's add-on build tooling; the container is not intended to run without Supervisor credentials.
