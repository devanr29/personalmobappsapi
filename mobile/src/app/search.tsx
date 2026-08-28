import { MagnifyingGlass } from "phosphor-react-native";
import { useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError } from "@/api/client";
import { search } from "@/api/search";
import type { SearchResult } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SearchBar } from "@/components/SearchBar";
import { Skeleton } from "@/components/Skeleton";
import { Tag } from "@/components/Tag";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Meter, clamp01 } from "@/components/charts";
import { AnimatedListItem } from "@/theme/motion";
import { Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function SearchScreen() {
  const theme = useTheme();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const result = await search(q);
      setResults(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't search right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Search" />
      <Stack p={4} pb={2}>
        <SearchBar value={query} onChangeText={setQuery} onSubmit={runSearch} placeholder="Search your notes and ideas…" />
      </Stack>

      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={56} radius={theme.radius.md} />
          <Skeleton height={56} radius={theme.radius.md} />
        </Stack>
      ) : error ? (
        <ErrorState message={error} onRetry={runSearch} />
      ) : results === null ? (
        <EmptyState message="Search across your notes and ideas." IconComponent={MagnifyingGlass} />
      ) : results.length === 0 ? (
        <EmptyState message="No matches found." IconComponent={MagnifyingGlass} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[2], gap: theme.spacing[3] }}>
          {results.map((result, index) => (
            <AnimatedListItem key={index} index={index}>
              <Card>
                <Stack gap={2}>
                  <Tag label={result.sourceType} variant="accent" />
                  <Text variant="body">{result.content}</Text>
                  <Meter value={clamp01(result.score)} />
                </Stack>
              </Card>
            </AnimatedListItem>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
