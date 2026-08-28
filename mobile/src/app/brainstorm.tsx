import { Brain } from "phosphor-react-native";
import { useState } from "react";
import { ActivityIndicator, ScrollView, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError } from "@/api/client";
import { brainstorm } from "@/api/brainstorm";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ScreenHeader } from "@/components/ScreenHeader";
import { PressableScale } from "@/theme/motion";
import { Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function BrainstormScreen() {
  const theme = useTheme();
  const [topic, setTopic] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    const q = topic.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    try {
      const { text } = await brainstorm(q);
      setResult(text);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't brainstorm right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Brainstorm" />
      <Stack p={4} pb={2} gap={3}>
        <TextInput
          value={topic}
          onChangeText={setTopic}
          onSubmitEditing={run}
          placeholder="What do you want to brainstorm?"
          placeholderTextColor={theme.colors.neutral[500]}
          style={{
            ...theme.type.body,
            color: theme.colors.text,
            backgroundColor: theme.colors.surface,
            borderRadius: theme.radius.pill,
            paddingVertical: theme.spacing[3],
            paddingHorizontal: theme.spacing[4],
          }}
          returnKeyType="go"
        />
        <PressableScale
          onPress={run}
          disabled={loading || topic.trim().length === 0}
          accessibilityRole="button"
          accessibilityLabel="Brainstorm"
          style={{
            alignSelf: "flex-start",
            flexDirection: "row",
            alignItems: "center",
            gap: theme.spacing[1.5],
            paddingVertical: theme.spacing[2],
            paddingHorizontal: theme.spacing[4],
            borderRadius: theme.radius.pill,
            backgroundColor: theme.colors.accent,
            opacity: loading || topic.trim().length === 0 ? 0.5 : 1,
          }}
        >
          {loading ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
          <Text variant="label" style={{ color: theme.colors.bg, fontFamily: theme.fontFamily.medium }}>
            Brainstorm
          </Text>
        </PressableScale>
      </Stack>

      {error ? (
        <ErrorState message={error} onRetry={run} />
      ) : result ? (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[2] }}>
          <Card>
            <Text variant="body">{result}</Text>
          </Card>
        </ScrollView>
      ) : !loading ? (
        <EmptyState message="Enter a topic to get ideas." IconComponent={Brain} />
      ) : null}
    </SafeAreaView>
  );
}
