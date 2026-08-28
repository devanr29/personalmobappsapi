const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function formatLongDate(date: Date): string {
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

export function formatEventTime(iso: string | null, allDay: boolean): string {
  if (!iso) return "";
  if (allDay) return "All day";
  const date = new Date(iso);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function formatGreeting(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return "Good morning,";
  if (hour < 18) return "Good afternoon,";
  return "Good evening,";
}

export function formatDayHeader(date: Date): string {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(date) - startOfDay(new Date())) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

// Backend sends naive Asia/Jakarta timestamps as "YYYY-MM-DD HH:MM" — a
// space, not "T", and no offset. That's not ISO 8601, so `new Date(...)` on
// it is engine-dependent (Hermes can return Invalid Date). Parse explicitly.
export function parseNaiveDateTime(value: string): Date | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hours, minutes] = match;
  return new Date(Number(year), Number(month) - 1, Number(day), Number(hours), Number(minutes));
}

export function formatReminderTime(iso: string): string {
  const target = parseNaiveDateTime(iso) ?? new Date(iso);
  const now = new Date();
  const isToday = target.toDateString() === now.toDateString();
  const hours = target.getHours().toString().padStart(2, "0");
  const minutes = target.getMinutes().toString().padStart(2, "0");
  return `${isToday ? "Today" : "Later"} · ${hours}:${minutes}`;
}
