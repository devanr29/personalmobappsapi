import { useCallback, useState } from "react";
import { ArrowClockwise, Eye } from "phosphor-react-native";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { ErrorState } from "@/components/ErrorState";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { getWalletSyncStatus, previewWalletSync, pullWalletSync } from "@/features/budget/api";
import type {
  WalletPullSummary,
  WalletSyncEntityResult,
  WalletSyncStatus,
} from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

type LastResult = { pull?: WalletPullSummary } | null;

export default function BudgetWalletSyncScreen() {
  const theme = useTheme();
  const { invalidate } = useBudgetRevision();
  const [busy, setBusy] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<LastResult>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetcher = useCallback(() => getWalletSyncStatus(), []);
  const { data, loading, error, refetch } = useResource<WalletSyncStatus>(fetcher, "Couldn't load sync status.");

  const runAction = (key: string, action: () => Promise<LastResult>) => {
    setBusy(key);
    setActionError(null);
    action()
      .then((result) => {
        setLastResult(result);
        invalidate();
        refetch();
      })
      .catch((err) => setActionError(err instanceof Error ? err.message : "Sync failed."))
      .finally(() => setBusy(null));
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Wallet Sync" />
      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={100} radius={theme.radius.md} />
          <Skeleton height={140} radius={theme.radius.md} />
        </Stack>
      ) : error || !data ? (
        <ErrorState message={error ?? "Couldn't load sync status."} onRetry={refetch} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], gap: theme.spacing[3] }}>
          <Text variant="caption" tone="faint">
            One-way pull from Wallet by BudgetBakers — nothing is ever sent out. Sync brings in your
            account balances and transactions only. Budgets, bills and goals are set up here in the app
            and are never touched by a sync.
          </Text>

          {!data.configured ? (
            <Card>
              <Stack gap={2}>
                <Text variant="cardTitle">Not configured</Text>
                <Text variant="label" tone="muted">
                  Set WALLET_API_TOKEN in environtment.env on the server, then reload this screen.
                </Text>
              </Stack>
            </Card>
          ) : (
            <>
              <StatusCard data={data} />

              <Card>
                <Stack gap={3}>
                  <Text variant="heading">Actions</Text>
                  <ActionRow
                    IconComponent={Eye}
                    label="Preview"
                    description="See what would change — nothing is written."
                    busy={busy === "preview"}
                    onPress={() => runAction("preview", () => previewWalletSync())}
                  />
                  <ActionRow
                    IconComponent={ArrowClockwise}
                    label="Sync"
                    description="Bring balances and transactions in from Wallet."
                    busy={busy === "sync"}
                    onPress={() => runAction("sync", () => pullWalletSync().then((r) => ({ pull: r.pull })))}
                  />
                </Stack>
              </Card>

              {actionError ? (
                <Card>
                  <Text variant="label" style={{ color: theme.status.short }}>
                    {actionError}
                  </Text>
                </Card>
              ) : null}

              {lastResult?.pull?.records?.hasMore ? (
                <Card>
                  <Text variant="label" tone="secondary">
                    Still catching up — Wallet has more history to page in. Tap Sync again to continue;
                    each run resumes where the last one stopped.
                  </Text>
                </Card>
              ) : null}

              {lastResult ? <ResultCard result={lastResult} /> : null}
            </>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function StatusCard({ data }: { data: WalletSyncStatus }) {
  const theme = useTheme();
  // Read the clock once per mount via a lazy initializer rather than on
  // every render — Date.now() in the render body is impure (react-hooks/purity),
  // and "expires within 14 days" doesn't need to track re-renders anyway.
  const [now] = useState(() => Date.now());
  const expiresSoon = data.tokenExpiresAt ? new Date(data.tokenExpiresAt).getTime() - now < 14 * 86_400_000 : false;

  return (
    <Card>
      <Stack gap={3}>
        <HStack justify="space-between">
          <Text variant="label" tone="secondary">
            Token expires
          </Text>
          <Text variant="meta" style={expiresSoon ? { color: theme.status.short } : undefined}>
            {data.tokenExpiresAt ? new Date(data.tokenExpiresAt).toLocaleDateString() : "unknown"}
          </Text>
        </HStack>
        <HStack justify="space-between">
          <Text variant="label" tone="secondary">
            Rate limit
          </Text>
          <Text variant="meta">
            {data.rateLimitRemaining ?? "—"} / {data.rateLimitLimit ?? "—"} left this hour
          </Text>
        </HStack>
        <HStack justify="space-between">
          <Text variant="label" tone="secondary">
            Last run
          </Text>
          <Text variant="meta">
            {data.lastRun ? `${data.lastRun.summary?.direction ?? ""} · ${new Date(data.lastRun.at).toLocaleString()}` : "never"}
          </Text>
        </HStack>
        <HStack justify="space-between">
          <Text variant="label" tone="secondary">
            Linked records
          </Text>
          <Text variant="meta">{data.linkCounts.record ?? 0}</Text>
        </HStack>
        {data.error ? (
          <Text variant="caption" style={{ color: theme.status.short }}>
            {data.error}
          </Text>
        ) : null}
      </Stack>
    </Card>
  );
}

function ActionRow({
  IconComponent,
  label,
  description,
  busy,
  onPress,
}: {
  IconComponent: React.ComponentType<{ size: number; color: string }>;
  label: string;
  description: string;
  busy: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <PressableScale onPress={busy ? undefined : onPress} accessibilityRole="button" accessibilityLabel={label}>
      <Box py={3} px={3} radius="md" bg={theme.colors.bg} style={{ opacity: busy ? 0.5 : 1 }}>
        <HStack align="center" gap={3}>
          <IconComponent size={18} color={theme.colors.accent} />
          <Stack flex={1} gap={0.5}>
            <Text variant="label">{busy ? `${label}…` : label}</Text>
            <Text variant="caption" tone="faint">
              {description}
            </Text>
          </Stack>
        </HStack>
      </Box>
    </PressableScale>
  );
}

function ResultCard({ result }: { result: LastResult }) {
  if (!result) return null;
  const sections: [string, Record<string, WalletSyncEntityResult>][] = [];
  if (result.pull) sections.push(["Pulled", result.pull as unknown as Record<string, WalletSyncEntityResult>]);

  return (
    <Card>
      <Stack gap={3}>
        <Text variant="heading">Result</Text>
        {sections.map(([label, entities]) => (
          <Stack key={label} gap={2}>
            <Text variant="label" tone="secondary">
              {label}
            </Text>
            {Object.entries(entities).map(([name, r]) => (
              <HStack key={name} justify="space-between">
                <Text variant="caption" tone="muted">
                  {name}
                </Text>
                <Text variant="caption" numeric>
                  +{r.created}
                  {r.updated !== undefined ? ` / ~${r.updated}` : ""}
                  {r.skipped.length ? ` / ${r.skipped.length} skipped` : ""}
                </Text>
              </HStack>
            ))}
            {Object.values(entities)
              .flatMap((r) => r.skipped)
              .slice(0, 5)
              .map((skip, i) => (
                <Text key={i} variant="caption" tone="faint">
                  · {skip.reason}
                </Text>
              ))}
          </Stack>
        ))}
      </Stack>
    </Card>
  );
}
