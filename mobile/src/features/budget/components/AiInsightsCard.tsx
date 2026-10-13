import { useCallback, useState } from "react";
import { ArrowClockwise, PaperPlaneRight, Sparkle } from "phosphor-react-native";
import { ActivityIndicator, TextInput } from "react-native";

import { ApiError } from "@/api/client";
import { Card } from "@/components/Card";
import { Skeleton } from "@/components/Skeleton";
import { askBudget, getAiInsights } from "@/features/budget/api";
import type { AiAnswer, AiInsights } from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

type AiResource = { insights: AiInsights | null };

/**
 * AI analysis of the current period plus a read-only "ask about your
 * budget" field. Fetched separately from the charts so a slow model call
 * never holds up the rest of the Insights screen — this card has its own
 * skeleton and quietly disappears on error.
 */
export function AiInsightsCard({ revision }: { revision: number }) {
  const theme = useTheme();
  const [refreshing, setRefreshing] = useState(false);
  const [override, setOverride] = useState<AiInsights | null>(null);

  // Wrapped like the insights fetcher in insights.tsx: a null result
  // (budget not set up) is a valid empty state, not a fetch failure.
  const fetcher = useCallback(async (): Promise<AiResource> => {
    setOverride(null);
    return { insights: await getAiInsights() };
  }, []);
  const { data, loading, error } = useResource<AiResource>(fetcher, "Couldn't load AI analysis.", revision);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverride(await getAiInsights(true));
    } catch {
      // Keep showing the last analysis; the refresh button stays available.
    } finally {
      setRefreshing(false);
    }
  }, []);

  if (error) return null;
  if (loading && !data) {
    return (
      <Card>
        <Stack gap={3}>
          <Skeleton height={18} width="40%" />
          <Skeleton height={14} />
          <Skeleton height={14} />
          <Skeleton height={14} width="80%" />
        </Stack>
      </Card>
    );
  }
  const insights = override ?? data?.insights;
  if (!insights) return null;

  return (
    <Card>
      <Stack gap={3}>
        <HStack align="center" justify="space-between">
          <HStack align="center" gap={2}>
            <Sparkle size={16} weight="fill" color={theme.colors.accent} />
            <Text variant="heading">AI analysis</Text>
          </HStack>
          <PressableScale
            onPress={refresh}
            disabled={refreshing}
            accessibilityRole="button"
            accessibilityLabel="Refresh AI analysis"
          >
            {refreshing ? (
              <ActivityIndicator size="small" color={theme.colors.accent} />
            ) : (
              <ArrowClockwise size={16} color={theme.colors.neutral[400]} />
            )}
          </PressableScale>
        </HStack>

        <Stack gap={2}>
          {insights.bullets.map((bullet, i) => (
            <HStack key={i} gap={2} align="flex-start">
              <Text variant="body" tone="accent">
                •
              </Text>
              <Text variant="body" style={{ flex: 1 }}>
                {bullet}
              </Text>
            </HStack>
          ))}
        </Stack>

        {insights.source === "rules" ? (
          <Text variant="caption" tone="faint">
            AI is unavailable right now, so these are the key numbers.
          </Text>
        ) : null}

        <AskField />
      </Stack>
    </Card>
  );
}

function AskField() {
  const theme = useTheme();
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AiAnswer | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const canAsk = !asking && question.trim().length > 0;

  const ask = useCallback(async () => {
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setAskError(null);
    try {
      setAnswer(await askBudget(q));
    } catch (err) {
      setAskError(err instanceof ApiError ? err.message : "Couldn't get an answer.");
    } finally {
      setAsking(false);
    }
  }, [question, asking]);

  return (
    <Stack gap={2}>
      <HStack align="center" gap={2} py={2} px={4} radius="pill" bg={theme.colors.bg}>
        <TextInput
          value={question}
          onChangeText={setQuestion}
          onSubmitEditing={ask}
          placeholder="Ask about your budget… e.g. can I afford 500k?"
          placeholderTextColor={theme.colors.neutral[500]}
          style={{ flex: 1, ...theme.type.body, color: theme.colors.text, padding: theme.spacing[0] }}
          returnKeyType="send"
          maxLength={500}
          accessibilityLabel="Ask a question about your budget"
        />
        <PressableScale
          onPress={ask}
          disabled={!canAsk}
          accessibilityRole="button"
          accessibilityLabel="Send question"
          style={{ opacity: canAsk ? 1 : 0.4 }}
        >
          {asking ? (
            <ActivityIndicator size="small" color={theme.colors.accent} />
          ) : (
            <PaperPlaneRight size={18} weight="fill" color={theme.colors.accent} />
          )}
        </PressableScale>
      </HStack>
      {askError ? (
        <Text variant="caption" tone="negative">
          {askError}
        </Text>
      ) : null}
      {answer ? (
        <Text variant="body" tone="secondary">
          {answer.answer}
        </Text>
      ) : null}
    </Stack>
  );
}
