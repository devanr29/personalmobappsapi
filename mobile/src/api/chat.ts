import { apiClient } from "./client";
import type { ChatResponse } from "./types";

export function sendChatMessage(message: string) {
  return apiClient.post<ChatResponse>("/api/chat", { message });
}

export function resetChat() {
  return apiClient.post<{ cleared: boolean }>("/api/chat/reset");
}
