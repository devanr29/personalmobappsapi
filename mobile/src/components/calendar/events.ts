import type { CalendarEvent } from "@/api/types";
import { wibDate, wibDayKey, wibParts } from "@/utils/date";

/** Parses an all-day "YYYY-MM-DD" as the WIB midnight starting that day. */
function parseDay(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return wibDate(y, m - 1, d);
}

export function eventStart(event: CalendarEvent): Date {
  if (!event.start) return new Date();
  return event.allDay ? parseDay(event.start) : new Date(event.start);
}

/** Exclusive end instant. Falls back to the start (timed) or the next day (all-day). */
export function eventEnd(event: CalendarEvent): Date {
  const start = eventStart(event);
  if (event.end) {
    const end = event.allDay ? parseDay(event.end) : new Date(event.end);
    if (end.getTime() > start.getTime()) return end;
  }
  if (!event.allDay) return start;
  const { year, month, day } = wibParts(start);
  return wibDate(year, month, day + 1);
}

const MAX_SPAN_DAYS = 62;

/** WIB day keys an event covers, so multi-day events show on every day. */
function eventDayKeys(event: CalendarEvent): string[] {
  const start = eventStart(event);
  // Last instant the event occupies; a zero-length timed event still counts on its start day.
  const last = new Date(Math.max(start.getTime(), eventEnd(event).getTime() - 1));
  const lastKey = wibDayKey(last);
  const { year, month, day } = wibParts(start);
  const keys: string[] = [];
  for (let i = 0; i < MAX_SPAN_DAYS; i += 1) {
    const key = wibDayKey(wibDate(year, month, day + i));
    keys.push(key);
    if (key === lastKey) break;
  }
  return keys;
}

/** Events bucketed by WIB day key; each day sorted all-day first, then by start. */
export function indexEventsByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const byDay = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    for (const key of eventDayKeys(event)) {
      const bucket = byDay.get(key);
      if (bucket) bucket.push(event);
      else byDay.set(key, [event]);
    }
  }
  for (const bucket of byDay.values()) {
    bucket.sort((a, b) => {
      if (a.allDay !== b.allDay) return a.allDay ? -1 : 1;
      return eventStart(a).getTime() - eventStart(b).getTime();
    });
  }
  return byDay;
}
