import { apiClient } from "./client";
import type { CalendarEvent } from "./types";

export function listEvents(days: number) {
  return apiClient.get<CalendarEvent[]>(`/api/events?days=${days}`);
}

export function createEvent(message: string) {
  return apiClient.post<{ created: boolean }>("/api/events", { message });
}

export function deleteEvent(id: string) {
  return apiClient.delete<{ id: string; deleted: boolean }>(`/api/events/${id}`);
}
