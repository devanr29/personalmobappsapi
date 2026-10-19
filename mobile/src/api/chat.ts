import { apiClient, LONG_REQUEST_TIMEOUT_MS } from "./client";
import type { ChatResponse } from "./types";

export function sendChatMessage(message: string) {
  // Some intents do several upstream calls plus an LLM (budget questions,
  // a first-time Quran verse reflection), so the default 35s is too tight.
  return apiClient.post<ChatResponse>("/api/chat", { message }, { timeoutMs: LONG_REQUEST_TIMEOUT_MS });
}

export function resetChat() {
  return apiClient.post<{ cleared: boolean }>("/api/chat/reset");
}
