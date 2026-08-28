import { apiClient } from "./client";
import type { NoteOrIdea } from "./types";

export function listNotes() {
  return apiClient.get<NoteOrIdea[]>("/api/notes");
}

export function createNote(message: string) {
  return apiClient.post<{ created: boolean }>("/api/notes", { message });
}

export function deleteNote(index: number) {
  return apiClient.delete<{ index: number; deleted: boolean }>(`/api/notes/${index}`);
}
