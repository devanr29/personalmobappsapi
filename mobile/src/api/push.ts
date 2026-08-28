import { apiClient } from "./client";

export function registerPushToken(token: string) {
  return apiClient.post<{ registered: boolean }>("/api/push/register", { token });
}
