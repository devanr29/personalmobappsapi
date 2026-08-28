import { useCallback, useState } from "react";
import { useRouter } from "expo-router";
import { CaretRight, Coins, Receipt, Target, TrendDown, TrendUp } from "phosphor-react-native";
import { Pressable, ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ListScreen } from "@/components/ListScreen";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { StatCard } from "@/components/StatCard";
import { ColumnChart, Dumbbell, DualLine, Heatmap, LineVsBaseline, Meter, Sparkline, StackedBar, clamp01 } from "@/components/charts";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { getInsights, getInsightsHistory } from "@/features/budget/api";
import type { BudgetHistory, BudgetInsights, BudgetVsActual } from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { AnimatedListItem } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah, formatRupiahCompact } from "@/utils/currency";

type HistoryGroupBy = "period" | "month";

// Fixed span for the column chart in both groupings — a like-for-like
// comparison of "last 12 months" vs "last 12 pay periods", no separate
// range control needed alongside the Period/Month toggle.
const HISTORY_SPAN = 12;

type InsightsResource = { insights: BudgetInsights | null };

export default function BudgetInsightsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { revision } = useBudgetRevision();
  const [groupBy, setGroupBy] = useState<HistoryGroupBy>("period");
  const [selected, setSelected] = useState<number | null>(null);

  // getInsights() resolves to null when the ledger isn't set up yet — that
  // is a valid, empty result, not a fetch failure, so it's wrapped in an
  // object here rather than passed straight to ListScreen's `data` prop
  // (which treats a bare `null` as the error state, not the empty state).
  const insightsFetcher = useCallback(async (): Promise<InsightsResource> => ({ insights: await getInsights() }), []);
  const { data, loading, error, refetch } = useResource<InsightsResource>(insightsFetcher, "Couldn't load insights.", revision);

  const historyFetcher = useCallback(() => getInsightsHistory(HISTORY_SPAN, groupBy), [groupBy]);
  const { data: history } = useResource<BudgetHistory>(historyFetcher, "Couldn't load history.", revision);

  // Toggling Period<->Month can shrink the array under a stale index, so
  // the active selection is clamped defensively rather than trusted —
  // the clamp is the safety net, resetting on toggle (below) is the UX.
  const selectedIndex = history ? Math.min(selected ?? history.periods.length - 1, history.periods.length - 1) : 0;
  const activePeriod = history?.periods[selectedIndex] ?? null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Insights" />
      <ListScreen
        data={data}
        loading={loading}
        error={error}
        refetch={refetch}
        skeleton={
          <Stack p={4} gap={4}>
            <Skeleton height={100} radius={theme.radius.md} />
            <Skeleton height={140} radius={theme.radius.md} />
            <Skeleton height={140} radius={theme.radius.md} />
          </Stack>
        }
      >
        {({ insights: data }) =>
          !data ? (
            <EmptyState message="No budget set up yet — nothing to show insights for." IconComponent={Target} />
          ) : (
          <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[5], gap: theme.spacing[4] }}>
            <Stack gap={0.5}>
              <Text variant="title">Insights</Text>
              <Text variant="caption" tone="muted">
                {data.period.label}
              </Text>
            </Stack>

            <StatsRow data={data} />

            <Card>
              <Stack gap={3}>
                <Text variant="heading">Daily spend</Text>
                <LineVsBaseline data={data.daily.map((d) => d.spend)} baseline={data.stats.dailyBudget} width={280} height={100} />
                <HStack justify="space-between">
                  <LegendDot color={theme.colors.accent} label="Spend" />
                  <LegendDot color={theme.chart.axis} label={`Daily budget (${formatRupiah(data.stats.dailyBudget)})`} />
                </HStack>
              </Stack>
            </Card>

            <Card>
              <Stack gap={3}>
                <HStack align="center" justify="space-between">
                  <Text variant="heading">Pace</Text>
                  <Text variant="caption" tone={data.pace.aheadBy >= 0 ? "positive" : "negative"}>
                    {data.pace.aheadBy >= 0 ? `Rp ${formatCompact(data.pace.aheadBy)} ahead` : `Rp ${formatCompact(-data.pace.aheadBy)} behind`}
                  </Text>
                </HStack>
                <DualLine
                  actual={data.pace.points.map((p) => p.actual)}
                  ideal={data.pace.points.map((p) => p.ideal)}
                  width={280}
                  height={100}
                />
                <HStack justify="space-between">
                  <LegendDot color={theme.colors.accent} label="Actual" />
                  <LegendDot color={theme.chart.axis} label="Ideal pace" />
                </HStack>
              </Stack>
            </Card>

            {data.categoriesTop.length > 0 ? (
              <Card>
                <Stack gap={3}>
                  <Text variant="heading">Where it&rsquo;s going</Text>
                  <Stack gap={3}>
                    {data.categoriesTop.map((c, i) => (
                      <AnimatedListItem key={c.categoryId ?? "other"} index={i}>
                        <CategoryRow
                          name={c.name}
                          spend={c.spend}
                          maxSpend={data.categoriesTop[0].spend}
                          color={theme.chart.sequential[Math.min(i, theme.chart.sequential.length - 1)]}
                        />
                      </AnimatedListItem>
                    ))}
                  </Stack>
                  <Pressable
                    onPress={() => router.push("/budget/category-patterns")}
                    accessibilityRole="button"
                    accessibilityLabel="See all category patterns"
                  >
                    <HStack align="center" justify="space-between">
                      <Text variant="caption" tone="accent">
                        See all category patterns
                      </Text>
                      <CaretRight size={12} color={theme.colors.accent} />
                    </HStack>
                  </Pressable>
                </Stack>
              </Card>
            ) : null}

            {data.budgetVsActual.length > 0 ? (
              <Card>
                <Stack gap={3}>
                  <Text variant="heading">Budget vs actual</Text>
                  <Stack gap={4}>
                    {data.budgetVsActual.map((item) => (
                      <BudgetVsActualRow key={item.categoryId} item={item} />
                    ))}
                  </Stack>
                </Stack>
              </Card>
            ) : null}

            <Card>
              <Stack gap={3}>
                <Text variant="heading">Spend calendar</Text>
                <Heatmap
                  cells={data.heatmap.cells.map((c) => ({ date: c.date, label: c.label, weekday: c.weekday, value: c.spend, count: c.count }))}
                  maxValue={data.heatmap.maxSpend}
                  formatValue={formatRupiah}
                />
              </Stack>
            </Card>

            {data.wallets.items.length > 0 ? (
              <Card>
                <Stack gap={3}>
                  <Text variant="heading">Where the money sits</Text>
                  <StackedBar
                    segments={data.wallets.items.map((w, i) => ({
                      value: Math.max(0, w.balance),
                      color: theme.chart.sequential[Math.min(i, theme.chart.sequential.length - 1)],
                    }))}
                    total={data.wallets.total}
                  />
                  <Stack gap={2}>
                    {data.wallets.items.map((w, i) => (
                      <HStack key={w.id} justify="space-between">
                        <LegendDot color={theme.chart.sequential[Math.min(i, theme.chart.sequential.length - 1)]} label={w.name} />
                        <Text variant="meta" tone="muted" numeric>
                          {formatRupiah(w.balance)}
                        </Text>
                      </HStack>
                    ))}
                  </Stack>
                </Stack>
              </Card>
            ) : null}

            {history && history.periods.length > 0 ? (
              <Card>
                <Stack gap={3}>
                  <HStack align="center" justify="space-between">
                    <Text variant="heading">Spend by {groupBy === "month" ? "month" : "period"}</Text>
                    <GroupByToggle
                      value={groupBy}
                      onChange={(next) => {
                        setSelected(null);
                        setGroupBy(next);
                      }}
                    />
                  </HStack>
                  {activePeriod ? (
                    <Stack gap={0.5}>
                      <Text variant="bigNumber" numeric>
                        {formatRupiah(activePeriod.spend)}
                      </Text>
                      <Text variant="caption" tone="muted">
                        {activePeriod.label}
                        {activePeriod.isCurrent ? " · so far" : ""} · {activePeriod.count} transaction
                        {activePeriod.count === 1 ? "" : "s"}
                      </Text>
                    </Stack>
                  ) : null}
                  <ColumnChart
                    data={history.periods.map((p) => ({
                      key: p.monthKey ?? String(p.periodId ?? p.label),
                      label: p.label,
                      shortLabel: p.shortLabel,
                      value: p.spend,
                      isPartial: p.isCurrent,
                    }))}
                    baseline={history.averageSpend || undefined}
                    baselineLabel="avg"
                    formatValue={formatRupiah}
                    formatAxisValue={formatRupiahCompact}
                    selectedIndex={selectedIndex}
                    onSelect={setSelected}
                  />
                  <HStack justify="space-between">
                    <LegendDot color={theme.colors.accent} label="Spend" />
                    <Text variant="caption" tone="muted">
                      Avg {formatRupiah(history.averageSpend)}
                    </Text>
                  </HStack>
                  {history.deltaVsPrevious ? (
                    <Text variant="caption" tone={history.deltaVsPrevious.spend <= 0 ? "positive" : "negative"}>
                      {history.deltaVsPrevious.spend <= 0 ? "Down" : "Up"} {formatRupiah(Math.abs(history.deltaVsPrevious.spend))} vs previous
                      {history.deltaVsPrevious.isPartial ? " (partial period)" : ""}
                    </Text>
                  ) : null}
                </Stack>
              </Card>
            ) : null}

            {history && history.periods.length > 0 ? (
              <Card>
                <Stack gap={3}>
                  <HStack align="center" justify="space-between">
                    <Text variant="heading">Income vs expense</Text>
                    <Text variant="caption" tone="muted">
                      Last {Math.min(6, history.periods.length)}
                    </Text>
                  </HStack>
                  <Stack gap={2}>
                    {history.periods.slice(-6).map((p) => (
                      <Stack key={p.monthKey ?? p.periodId ?? p.label} gap={1}>
                        <HStack justify="space-between">
                          <Text variant="caption" tone="muted">
                            {p.label}
                          </Text>
                          <Text variant="caption" tone={p.net >= 0 ? "positive" : "negative"} numeric>
                            {p.net >= 0 ? "+" : ""}
                            {formatRupiah(p.net)}
                          </Text>
                        </HStack>
                        <StackedBar
                          segments={[
                            { value: p.income, color: theme.chart.categorical[0] },
                            { value: p.spend, color: theme.chart.categorical[1] },
                          ]}
                        />
                      </Stack>
                    ))}
                  </Stack>
                  <HStack justify="space-between">
                    <LegendDot color={theme.chart.categorical[0]} label="Income" />
                    <LegendDot color={theme.chart.categorical[1]} label="Expense" />
                  </HStack>
                </Stack>
              </Card>
            ) : null}
          </ScrollView>
          )
        }
      </ListScreen>
    </SafeAreaView>
  );
}

function formatCompact(n: number): string {
  const rounded = Math.round(Math.abs(n));
  return rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function StatsRow({ data }: { data: BudgetInsights }) {
  return (
    <Stack gap={3}>
      <HStack gap={3}>
        <StatCard
          IconComponent={Coins}
          value={formatRupiah(data.stats.spendToDate)}
          label="Spent to date"
          trend={<Sparkline data={data.stats.spendSparkline} width={64} height={24} />}
        />
        <StatCard
          IconComponent={data.stats.burnRateVsIdeal <= 0 ? TrendDown : TrendUp}
          value={formatRupiah(data.stats.avgDailySpend)}
          valueTone={data.stats.burnRateVsIdeal <= 0 ? "positive" : "negative"}
          label="Avg daily spend"
        />
      </HStack>
      <HStack gap={3}>
        <StatCard IconComponent={Target} value={formatRupiah(data.stats.projectedEndBalance)} label="Projected at payday" />
        <StatCard
          IconComponent={Receipt}
          value={data.stats.largestExpense ? formatRupiah(data.stats.largestExpense.amount) : "—"}
          label={data.stats.largestExpense ? data.stats.largestExpense.name : "Largest expense"}
        />
      </HStack>
    </Stack>
  );
}

function CategoryRow({ name, spend, maxSpend, color }: { name: string; spend: number; maxSpend: number; color: string }) {
  const progress = maxSpend > 0 ? clamp01(spend / maxSpend) : 0;
  return (
    <Stack gap={1.5}>
      <HStack justify="space-between">
        <Text variant="label">{name}</Text>
        <Text variant="meta" tone="muted" numeric>
          {formatRupiah(spend)}
        </Text>
      </HStack>
      <Meter value={progress} color={color} />
    </Stack>
  );
}

function BudgetVsActualRow({ item }: { item: BudgetVsActual }) {
  const theme = useTheme();
  const scale = Math.max(item.budget, item.actual, 1);
  const isOver = item.overBudget > 0;
  return (
    <Stack gap={1.5}>
      <HStack justify="space-between">
        <Text variant="label">{item.name}</Text>
        <Text variant="meta" tone={isOver ? "negative" : "muted"} numeric>
          {formatRupiah(item.actual)} of {formatRupiah(item.budget)}
        </Text>
      </HStack>
      <Dumbbell from={item.budget / scale} to={item.actual / scale} color={isOver ? theme.status.short : theme.colors.accent} />
    </Stack>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  const theme = useTheme();
  return (
    <HStack align="center" gap={1.5}>
      <View style={{ width: 8, height: 8, borderRadius: theme.radius.full, backgroundColor: color }} />
      <Text variant="caption" tone="muted">
        {label}
      </Text>
    </HStack>
  );
}

function GroupByToggle({ value, onChange }: { value: HistoryGroupBy; onChange: (v: HistoryGroupBy) => void }) {
  const theme = useTheme();
  return (
    <HStack gap={1} bg={theme.colors.neutral[800]} radius="pill" p={0.5}>
      {(["period", "month"] as const).map((option) => (
        <Pressable
          key={option}
          onPress={() => onChange(option)}
          accessibilityRole="button"
          accessibilityLabel={option === "period" ? "Group by pay period" : "Group by calendar month"}
        >
          <Stack
            py={1}
            px={3}
            radius="pill"
            bg={value === option ? theme.colors.accentRamp[900] : "transparent"}
          >
            <Text variant="caption" tone={value === option ? "accent" : "muted"}>
              {option === "period" ? "Period" : "Month"}
            </Text>
          </Stack>
        </Pressable>
      ))}
    </HStack>
  );
}
