// The backend sends every budget timestamp (occurredAt) as a naive
// Asia/Jakarta "YYYY-MM-DD HH:MM" string — not ISO 8601. `new Date(...)` on
// that is engine-dependent (Hermes can return Invalid Date on-device even
// when it works on web). Route every budget date through here instead of a
// bare `new Date(apiString)`.
import { formatDayHeader, parseNaiveDateTime, toNaiveDateTime, wibDayKey, wibParts } from "@/utils/date";

export { toNaiveDateTime };

export function parseBudgetDate(occurredAt: string): Date {
  return parseNaiveDateTime(occurredAt) ?? new Date(occurredAt);
}

export function formatBudgetDayHeader(occurredAt: string): string {
  return formatDayHeader(parseBudgetDate(occurredAt));
}

export function formatBudgetTime(occurredAt: string): string {
  const { hours, minutes } = wibParts(parseBudgetDate(occurredAt));
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function budgetDayKey(occurredAt: string): string {
  return wibDayKey(parseBudgetDate(occurredAt));
}
