import { Newspaper, X } from "phosphor-react-native";
import { useState } from "react";
import { ActivityIndicator, Modal, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError } from "@/api/client";
import { getNewsArticle, searchNews } from "@/api/news";
import type { NewsArticle } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { GlassSurface } from "@/components/GlassSurface";
import { ScreenHeader } from "@/components/ScreenHeader";
import { SearchBar } from "@/components/SearchBar";
import { Skeleton } from "@/components/Skeleton";
import { AnimatedListItem, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function NewsScreen() {
  const theme = useTheme();
  const [topic, setTopic] = useState("");
  const [articles, setArticles] = useState<NewsArticle[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<NewsArticle | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const runSearch = async () => {
    const q = topic.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const result = await searchNews(q);
      setArticles(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load news.");
    } finally {
      setLoading(false);
    }
  };

  const openArticle = async (article: NewsArticle) => {
    setSelected(article);
    setSummary(null);
    setSummaryLoading(true);
    try {
      const result = await getNewsArticle(article);
      setSummary(result.summary);
    } catch (err) {
      setSummary(err instanceof ApiError ? err.message : "Couldn't load the full article.");
    } finally {
      setSummaryLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="News" />
      <Stack p={4} pb={2}>
        <SearchBar value={topic} onChangeText={setTopic} onSubmit={runSearch} placeholder="Search a topic…" />
      </Stack>

      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={70} radius={theme.radius.md} />
          <Skeleton height={70} radius={theme.radius.md} />
        </Stack>
      ) : error ? (
        <ErrorState message={error} onRetry={runSearch} />
      ) : articles === null ? (
        <EmptyState message="Search a topic to see recent articles." IconComponent={Newspaper} />
      ) : articles.length === 0 ? (
        <EmptyState message="No articles found for that topic." IconComponent={Newspaper} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[2], gap: theme.spacing[3] }}>
          {articles.map((article, i) => (
            <AnimatedListItem key={article.url} index={i}>
              <PressableScale onPress={() => openArticle(article)}>
                <Card>
                  <Stack gap={1}>
                    <Text variant="bodyStrong">{article.title}</Text>
                    <Text variant="caption" tone="muted">
                      {article.source} · {article.publishedAt}
                    </Text>
                  </Stack>
                </Card>
              </PressableScale>
            </AnimatedListItem>
          ))}
        </ScrollView>
      )}

      <Modal visible={selected !== null} animationType="slide" onRequestClose={() => setSelected(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }}>
          <GlassSurface style={{ borderBottomWidth: 1, borderBottomColor: theme.colors.divider }}>
            <HStack align="center" justify="space-between" py={3} px={4}>
              <Text variant="cardTitle">Article</Text>
              <PressableScale onPress={() => setSelected(null)} accessibilityRole="button" accessibilityLabel="Close" hitSlop={8}>
                <X size={20} color={theme.colors.text} />
              </PressableScale>
            </HStack>
          </GlassSurface>
          {summaryLoading ? (
            <Stack flex={1} align="center" justify="center">
              <ActivityIndicator color={theme.colors.accent} />
            </Stack>
          ) : (
            <ScrollView contentContainerStyle={{ padding: theme.spacing[4] }}>
              <Text variant="body">{summary}</Text>
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}
