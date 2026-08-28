import { apiClient } from "./client";
import type { Task } from "./types";

export function listTasks() {
  return apiClient.get<Task[]>("/api/tasks");
}

export function completeTask(id: string) {
  return apiClient.patch<Task>(`/api/tasks/${id}/complete`);
}

export function deleteTask(id: string) {
  return apiClient.delete<{ id: string }>(`/api/tasks/${id}`);
}
