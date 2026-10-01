import "../household_calendar/www/household-calendar-card.js";

const today = new Date();
today.setHours(12, 0, 0, 0);
today.setDate(today.getDate() - ((today.getDay() + 6) % 7));
const formatDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const paidOccurrences = new Set();
const netflixDue = new Date();
netflixDue.setHours(12, 0, 0, 0);
netflixDue.setDate(netflixDue.getDate() + 1);
const netflixDueDate = formatDate(netflixDue);
const eventsForWeek = (monday) => {
  const nextMonday = new Date(`${monday}T12:00:00`);
  nextMonday.setDate(nextMonday.getDate() + 7);
  if (netflixDueDate < monday || netflixDueDate >= formatDate(nextMonday)) return [];
  return [{
    id: 1,
    title: "Netflix",
    date: netflixDueDate,
    paid: paidOccurrences.has(`1:${netflixDueDate}`),
  }];
};

const mondayOf = (isoDate) => {
  const date = new Date(`${isoDate}T12:00:00`);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return formatDate(date);
};

const card = document.querySelector("household-calendar-card");
const mockHass = {
  config: { time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone },
  locale: { language: navigator.language || "en" },
  states: {},
  callWS: async (command) => {
    const data = command.event_data || {};
    if (command.event_type === "household_calendar_week_requested") {
      await publishWeek(mondayOf(data.monday));
    } else if (command.event_type === "household_calendar_paid") {
      const key = `${data.event_id}:${data.due_date}`;
      if (data.paid) paidOccurrences.add(key);
      else paidOccurrences.delete(key);
      await publishWeek(mockHass.states["sensor.household_calendar_week"].attributes.monday);
    }
    return { success: true };
  },
};

async function publishWeek(monday) {
  mockHass.states["sensor.household_calendar_week"] = {
    state: "5",
    attributes: { monday, events: eventsForWeek(monday) },
  };
  card.hass = mockHass;
}

await customElements.whenDefined("household-calendar-card");
card.setConfig({});
await publishWeek(formatDate(today));
