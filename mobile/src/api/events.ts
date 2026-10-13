import { apiClient } from "./client";
import type { CalendarEvent } from "./types";

export function listEvents(days: number) {
  return apiClient.get<CalendarEvent[]>(`/api/events?days=${days}`);
}

/** Events overlapping the WIB days `start`..`end` ("YYYY-MM-DD", inclusive). */
export function listEventsRange(start: string, end: string) {
  return apiClient.get<CalendarEvent[]>(`/api/events?start=${start}&end=${end}`);
}

export function createEvent(message: string) {
  return apiClient.post<{ created: boolean }>("/api/events", { message });
}

export function deleteEvent(id: string) {
  return apiClient.delete<{ id: string; deleted: boolean }>(`/api/events/${id}`);
}
