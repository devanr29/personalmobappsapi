import { apiClient } from "./client";
import type { Reminder } from "./types";

export function listReminders() {
  return apiClient.get<Reminder[]>("/api/reminders");
}

export function createReminder(message: string) {
  return apiClient.post<{ created: boolean }>("/api/reminders", { message });
}

export function deleteReminder(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean }>(`/api/reminders/${id}`);
}
