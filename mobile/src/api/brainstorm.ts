import { apiClient } from "./client";

export function brainstorm(topic: string) {
  return apiClient.post<{ text: string }>("/api/brainstorm", { topic });
}
