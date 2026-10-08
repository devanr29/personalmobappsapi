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

// The app runs on Asia/Jakarta (WIB, UTC+7, no DST) regardless of the
// device's timezone. Dates are real instants; read wall-clock fields only
// through wibParts/wibDate, never through Date's local getters.
const WIB_OFFSET_MS = 7 * 60 * 60 * 1000;

export type WibParts = {
  year: number;
  month: number; // 0-11, like Date#getMonth
  day: number;
  weekday: number; // 0=Sunday, like Date#getDay
  hours: number;
  minutes: number;
};

export function wibParts(date: Date): WibParts {
  const shifted = new Date(date.getTime() + WIB_OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth(),
    day: shifted.getUTCDate(),
    weekday: shifted.getUTCDay(),
    hours: shifted.getUTCHours(),
    minutes: shifted.getUTCMinutes(),
  };
}

/** The instant at the given WIB wall-clock time. Out-of-range fields roll
 * over like the Date constructor (e.g. day + 1 at month end). */
export function wibDate(year: number, month: number, day: number, hours = 0, minutes = 0): Date {
  return new Date(Date.UTC(year, month, day, hours, minutes) - WIB_OFFSET_MS);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "YYYY-MM-DD" of the WIB calendar day containing `date`. */
export function wibDayKey(date: Date): string {
  const { year, month, day } = wibParts(date);
  return `${year}-${pad(month + 1)}-${pad(day)}`;
}

function formatClock(date: Date): string {
  const { hours, minutes } = wibParts(date);
  return `${pad(hours)}:${pad(minutes)}`;
}

export function formatLongDate(date: Date): string {
  const { weekday, month, day } = wibParts(date);
  return `${WEEKDAYS[weekday]}, ${MONTHS[month]} ${day}`;
}

/** e.g. "Oct 8, 2026" in WIB. */
export function formatShortDate(date: Date): string {
  const { year, month, day } = wibParts(date);
  return `${MONTHS[month].slice(0, 3)} ${day}, ${year}`;
}

/** e.g. "Oct 8, 2026 14:05" in WIB. */
export function formatShortDateTime(date: Date): string {
  return `${formatShortDate(date)} ${formatClock(date)}`;
}

export function formatEventTime(iso: string | null, allDay: boolean): string {
  if (!iso) return "";
  if (allDay) return "All day";
  return formatClock(new Date(iso));
}

export function formatGreeting(date: Date): string {
  const { hours } = wibParts(date);
  if (hours < 12) return "Good morning,";
  if (hours < 18) return "Good afternoon,";
  return "Good evening,";
}

export function formatDayHeader(date: Date): string {
  const target = wibParts(date);
  const today = wibParts(new Date());
  const diffDays = Math.round(
    (Date.UTC(target.year, target.month, target.day) - Date.UTC(today.year, today.month, today.day)) / 86400000,
  );
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  return `${WEEKDAYS[target.weekday]}, ${MONTHS[target.month]} ${target.day}`;
}

// Backend sends naive Asia/Jakarta timestamps as "YYYY-MM-DD HH:MM" — a
// space, not "T", and no offset. That's not ISO 8601, so `new Date(...)` on
// it is engine-dependent (Hermes can return Invalid Date). Parse explicitly.
export function parseNaiveDateTime(value: string): Date | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hours, minutes] = match;
  return wibDate(Number(year), Number(month) - 1, Number(day), Number(hours), Number(minutes));
}

/** Inverse of parseNaiveDateTime: formats an instant as the naive WIB
 * "YYYY-MM-DD HH:MM" string the backend expects. */
export function toNaiveDateTime(date: Date): string {
  return `${wibDayKey(date)} ${formatClock(date)}`;
}

export function formatReminderTime(iso: string): string {
  const target = parseNaiveDateTime(iso) ?? new Date(iso);
  const isToday = wibDayKey(target) === wibDayKey(new Date());
  return `${isToday ? "Today" : "Later"} · ${formatClock(target)}`;
}
