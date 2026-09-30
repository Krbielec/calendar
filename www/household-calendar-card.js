class HouseholdCalendarCard extends HTMLElement {
  constructor() {
    super();
    this._weekStart = null;
    this._lastRequested = null;
    this._pending = new Set();
    this._overrides = new Map();
  }

  setConfig(config) {
    this.config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) this._build();

    if (!this._weekStart) this._weekStart = this._monday(this._today(hass));
    const attributes = hass.states["sensor.household_calendar_week"]?.attributes || {};
    if (attributes.monday === this._weekStart) {
      this._lastRequested = null;
      for (const event of attributes.events || []) {
        const key = this._eventKey(event);
        if (this._overrides.get(key) === event.paid) {
          this._overrides.delete(key);
          this._pending.delete(key);
        }
      }
    } else if (this._lastRequested !== this._weekStart) {
      this._requestWeek(this._weekStart);
    }
    this._render(attributes.monday === this._weekStart ? attributes : null);
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:16px; }
        .header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
        .title { text-align:center; font-weight:600; color:var(--primary-text-color); }
        .range { margin-top:4px; font-size:.85em; color:var(--secondary-text-color); }
        button { font:inherit; }
        .nav, .paid { border:0; border-radius:8px; cursor:pointer; }
        .nav { width:40px; height:40px; color:var(--primary-color); background:var(--secondary-background-color); font-size:1.5em; }
        .days { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:8px; }
        .day { min-width:0; border:1px solid var(--divider-color); border-radius:8px; padding:8px; background:var(--card-background-color); }
        .day.today { border-color:var(--primary-color); }
        .day-heading { margin-bottom:8px; font-size:.8em; font-weight:700; color:var(--secondary-text-color); text-transform:uppercase; }
        .event { margin:6px 0; padding:8px; border-radius:7px; background:var(--secondary-background-color); overflow-wrap:anywhere; }
        .event.paid .event-name { text-decoration:line-through; opacity:.65; }
        .event-name { font-size:.9em; line-height:1.3; margin-bottom:7px; }
        .paid { width:100%; min-height:30px; padding:5px 7px; color:var(--primary-text-color); background:var(--divider-color); font-size:.78em; }
        .event.paid .paid { background:var(--success-color,#2e7d32); color:#fff; }
        .empty, .message { color:var(--secondary-text-color); font-size:.8em; }
        .message { text-align:center; padding:18px 4px; }
        @media (max-width:700px) {
          .days { grid-template-columns:1fr; }
          .day { display:grid; grid-template-columns:74px minmax(0,1fr); gap:8px; }
          .day-heading { margin:5px 0 0; }
        }
      </style>
      <ha-card>
        <div class="header">
          <button class="nav" data-action="previous" aria-label="Previous week">‹</button>
          <div class="title"><div>Household calendar</div><div class="range"></div></div>
          <button class="nav" data-action="next" aria-label="Next week">›</button>
        </div>
        <div class="content"></div>
      </ha-card>`;
    root.addEventListener("click", (event) => this._handleClick(event));
  }

  _today(hass) {
    const zone = hass.config?.time_zone;
    if (zone) {
      const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
      }).formatToParts(new Date());
      const value = (type) => parts.find((part) => part.type === type).value;
      return `${value("year")}-${value("month")}-${value("day")}`;
    }
    return this._dateString(new Date());
  }

  _dateString(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  _monday(isoDate) {
    const date = new Date(`${isoDate}T12:00:00`);
    date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
    return this._dateString(date);
  }

  _shiftWeek(isoDate, weeks) {
    const date = new Date(`${isoDate}T12:00:00`);
    date.setDate(date.getDate() + Math.round(weeks * 7));
    return this._dateString(date);
  }

  _requestWeek(monday) {
    this._lastRequested = monday;
    this._hass.callWS({
      type: "fire_event",
      event_type: "household_calendar_week_requested",
      event_data: { monday },
    }).catch((error) => console.error("Household Calendar week request failed", error));
  }

  _eventKey(event) {
    return `${event.id}:${event.date}`;
  }

  _handleClick(click) {
    const button = click.composedPath().find((node) => node?.dataset?.action || node?.dataset?.eventId);
    if (!button) return;
    if (button.dataset.action) {
      this._weekStart = this._shiftWeek(this._weekStart, button.dataset.action === "previous" ? -1 : 1);
      this._lastRequested = null;
      this._render(null);
      this._requestWeek(this._weekStart);
      return;
    }

    const eventId = Number(button.dataset.eventId);
    const dueDate = button.dataset.eventDate;
    const attrs = this._hass.states["sensor.household_calendar_week"]?.attributes || {};
    const event = (attrs.events || []).find((item) => item.id === eventId && item.date === dueDate);
    if (!event || !Number.isSafeInteger(eventId)) return;
    const key = this._eventKey(event);
    if (this._pending.has(key)) return;
    const paid = !(this._overrides.has(key) ? this._overrides.get(key) : event.paid);
    this._overrides.set(key, paid);
    this._pending.add(key);
    this._render(attrs);
    const retryTimer = window.setTimeout(() => {
      if (!this._pending.delete(key)) return;
      this._overrides.delete(key);
      this._render(this._hass.states["sensor.household_calendar_week"]?.attributes || null);
    }, 10000);
    this._hass.callWS({
      type: "fire_event",
      event_type: "household_calendar_paid",
      event_data: { event_id: eventId, due_date: dueDate, paid },
    }).catch((error) => {
      console.error("Household Calendar paid-state update failed", error);
      window.clearTimeout(retryTimer);
      this._pending.delete(key);
      this._overrides.delete(key);
      this._render(attrs);
    });
  }

  _render(attributes) {
    if (!this.shadowRoot) return;
    const range = this.shadowRoot.querySelector(".range");
    const content = this.shadowRoot.querySelector(".content");
    const monday = this._weekStart;
    const startDate = new Date(`${monday}T12:00:00`);
    const sundayDate = new Date(`${this._shiftWeek(monday, 1)}T12:00:00`);
    sundayDate.setDate(sundayDate.getDate() - 1);
    const locale = this._hass?.locale?.language || "en";
    range.textContent = `${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(startDate)} – ${new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(sundayDate)}`;

    if (!attributes) {
      content.innerHTML = '<div class="message">Loading events…</div>';
      return;
    }
    const eventsByDate = new Map();
    for (const event of attributes.events || []) {
      const events = eventsByDate.get(event.date) || [];
      events.push(event);
      eventsByDate.set(event.date, events);
    }
    const today = this._today(this._hass);
    const dayFormatter = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short" });
    const days = [];
    for (let index = 0; index < 7; index += 1) {
      const day = new Date(`${monday}T12:00:00`);
      day.setDate(day.getDate() + index);
      const dateString = this._dateString(day);
      const events = eventsByDate.get(dateString) || [];
      const cards = events.map((event) => {
        const key = this._eventKey(event);
        const paid = this._overrides.has(key) ? this._overrides.get(key) : event.paid;
        const pending = this._pending.has(key);
        return `<div class="event ${paid ? "paid" : ""}">
          <div class="event-name">${this._escape(event.title)}</div>
          <button class="paid" data-event-id="${Number(event.id)}" data-event-date="${this._escape(event.date)}" ${pending ? "disabled" : ""}>
            ${pending ? "Saving…" : paid ? "Paid · undo" : "Mark paid"}
          </button>
        </div>`;
      }).join("");
      days.push(`<section class="day ${dateString === today ? "today" : ""}">
        <div class="day-heading">${this._escape(dayFormatter.format(day))}</div>
        <div>${cards || '<div class="empty">No events</div>'}</div>
      </section>`);
    }
    content.innerHTML = `<div class="days">${days.join("")}</div>`;
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  getCardSize() {
    return 5;
  }
}

customElements.define("household-calendar-card", HouseholdCalendarCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "household-calendar-card",
  name: "Household Calendar",
  description: "Weekly, day-grouped household events",
});
