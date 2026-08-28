import { apiClient } from "./client";
import type { NewsArticle } from "./types";

export function searchNews(topic: string) {
  return apiClient.get<NewsArticle[]>(`/api/news?topic=${encodeURIComponent(topic)}`);
}

export function getNewsArticle(article: NewsArticle) {
  const params = new URLSearchParams({
    url: article.url,
    title: article.title,
    source: article.source,
    publishedAt: article.publishedAt,
    description: article.description,
  });
  return apiClient.get<{ summary: string }>(`/api/news/article?${params.toString()}`);
}
