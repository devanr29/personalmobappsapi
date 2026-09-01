import { useCallback, useState } from "react";
import { ArrowsLeftRight, Bell, CalendarBlank, Gear, Warning, type Icon } from "phosphor-react-native";
import { Pressable, ScrollView, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { IconBadge, type IconBadgeTone } from "@/components/IconBadge";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { getAlertPrefs, listAlerts, markAlertRead, updateAlertPrefs } from "@/features/budget/api";
import type { Alert, AlertKind, AlertPrefs } from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

type AlertsResource = { alerts: Alert[]; unreadCount: number; prefs: AlertPrefs };

export default function BudgetAlertsScreen() {
  const theme = useTheme();
  const [prefsOpen, setPrefsOpen] = useState(false);

  const fetcher = useCallback(async (): Promise<AlertsResource> => {
    const [{ items, unreadCount }, prefs] = await Promise.all([listAlerts(false, 30), getAlertPrefs()]);
    return { alerts: items, unreadCount, prefs };
  }, []);
  const { data, loading, error, refetch } = useResource<AlertsResource>(fetcher, "Couldn't load alerts.");

  const handleTapAlert = (alert: Alert) => {
    if (alert.readAt) return;
    markAlertRead(alert.id).finally(refetch);
  };

  const handlePrefChange = (patch: Partial<AlertPrefs>) => {
    updateAlertPrefs(patch).finally(refetch);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Alerts" />
      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={80} radius={theme.radius.md} />
          <Skeleton height={56} radius={theme.radius.md} />
          <Skeleton height={56} radius={theme.radius.md} />
        </Stack>
      ) : error || !data ? (
        <ErrorState message={error ?? "Couldn't load alerts."} onRetry={refetch} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], gap: theme.spacing[3] }}>
          <Card>
            <Stack gap={3}>
              <PressableScale onPress={() => setPrefsOpen((v) => !v)} accessibilityRole="button" accessibilityLabel="Toggle alert settings">
                <HStack align="center" gap={2}>
                  <Gear size={16} color={theme.colors.accent} />
                  <Text variant="label" tone="secondary" style={{ flex: 1 }}>
                    Alert settings
                  </Text>
                  <Text variant="caption" tone="muted">
                    {prefsOpen ? "Hide" : "Show"}
                  </Text>
                </HStack>
              </PressableScale>
              {prefsOpen ? (
                <Stack gap={3}>
                  <PrefRow
                    label="Daily check-in"
                    value={data.prefs.dailyCheckinEnabled}
                    onChange={(v) => handlePrefChange({ dailyCheckinEnabled: v })}
                  />
                  <PrefRow
                    label="Over-budget warnings"
                    value={data.prefs.overBudgetEnabled}
                    onChange={(v) => handlePrefChange({ overBudgetEnabled: v })}
                  />
                  <Text variant="caption" tone="faint">
                    Bills alert {data.prefs.billDueLeadDays} day{data.prefs.billDueLeadDays === 1 ? "" : "s"} before due;
                    over-budget triggers at {data.prefs.overBudgetThresholdPct}% of a category&rsquo;s limit.
                  </Text>
                </Stack>
              ) : null}
            </Stack>
          </Card>

          {data.alerts.length === 0 ? (
            <EmptyState message="No alerts yet." IconComponent={Bell} />
          ) : (
            <Stack gap={2}>
              {data.alerts.map((alert) => (
                <AlertRow key={alert.id} alert={alert} onPress={() => handleTapAlert(alert)} />
              ))}
            </Stack>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function PrefRow({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  const theme = useTheme();
  return (
    <HStack align="center" justify="space-between">
      <Text variant="label">{label}</Text>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: theme.colors.neutral[700], true: theme.colors.accent }}
      />
    </HStack>
  );
}

function alertIconFor(kind: AlertKind): { IconComponent: Icon; tone: IconBadgeTone } {
  switch (kind) {
    case "over_budget":
    case "low_daily_budget":
      return { IconComponent: Warning, tone: "negative" };
    case "bill_due":
      return { IconComponent: CalendarBlank, tone: "tight" };
    case "period_rollover":
      return { IconComponent: ArrowsLeftRight, tone: "accent" };
    case "daily_checkin":
    default:
      return { IconComponent: Bell, tone: "accent" };
  }
}

function AlertRow({ alert, onPress }: { alert: Alert; onPress: () => void }) {
  const isUnread = !alert.readAt;
  const { IconComponent, tone } = alertIconFor(alert.kind);

  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={alert.title}>
      <Card style={isUnread ? undefined : { opacity: 0.6 }}>
        <HStack gap={3} align="flex-start">
          <IconBadge IconComponent={IconComponent} tone={tone} size={32} />
          <Stack flex={1} gap={0.5}>
            <Text variant="bodyStrong" tone={isUnread ? "primary" : "muted"}>
              {alert.title}
            </Text>
            <Text variant="caption" tone="muted">
              {alert.body}
            </Text>
          </Stack>
        </HStack>
      </Card>
    </Pressable>
  );
}
