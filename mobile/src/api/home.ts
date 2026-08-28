import { apiClient } from "./client";
import type { HomeResponse } from "./types";

export function getHome() {
  return apiClient.get<HomeResponse>("/api/home");
}
