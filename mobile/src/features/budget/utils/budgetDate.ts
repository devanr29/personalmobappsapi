// The backend sends every budget timestamp (occurredAt) as a naive
// Asia/Jakarta "YYYY-MM-DD HH:MM" string — not ISO 8601. `new Date(...)` on
// that is engine-dependent (Hermes can return Invalid Date on-device even
// when it works on web). Route every budget date through here instead of a
// bare `new Date(apiString)`.
import { formatDayHeader, parseNaiveDateTime } from "@/utils/date";

export function parseBudgetDate(occurredAt: string): Date {
  return parseNaiveDateTime(occurredAt) ?? new Date(occurredAt);
}

export function formatBudgetDayHeader(occurredAt: string): string {
  return formatDayHeader(parseBudgetDate(occurredAt));
}

export function formatBudgetTime(occurredAt: string): string {
  const date = parseBudgetDate(occurredAt);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function budgetDayKey(occurredAt: string): string {
  const date = parseBudgetDate(occurredAt);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/** Inverse of parseBudgetDate: formats a local Date as the naive
 * "YYYY-MM-DD HH:MM" string the backend expects for occurredAt. Uses the
 * device's local clock, not UTC — correct as long as the device is set to
 * Asia/Jakarta, the only timezone this app supports. */
export function toNaiveDateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
