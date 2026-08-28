import { apiClient } from "./client";
import type { SearchResult } from "./types";

export function search(query: string) {
  return apiClient.get<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}`);
}
