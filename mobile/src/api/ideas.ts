import { apiClient } from "./client";
import type { NoteOrIdea } from "./types";

export function listIdeas() {
  return apiClient.get<NoteOrIdea[]>("/api/ideas");
}

export function createIdea(message: string) {
  return apiClient.post<{ created: boolean }>("/api/ideas", { message });
}

export function deleteIdea(index: number) {
  return apiClient.delete<{ index: number; deleted: boolean }>(`/api/ideas/${index}`);
}
