import { useCallback } from "react";
import { Target } from "phosphor-react-native";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ExpandableCard } from "@/components/ExpandableCard";
import { ListScreen } from "@/components/ListScreen";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { ColumnChart, Sparkline } from "@/components/charts";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { getCategoryPatterns } from "@/features/budget/api";
import type { CategoryPattern, CategoryPatternTag, CategoryPatterns } from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme, type Theme } from "@/theme/ThemeProvider";
import { formatRupiah, formatRupiahCompact } from "@/utils/currency";

// The imported Wallet-sync taxonomy (Advisory, Bar cafe, Unknown expense, …)
// carries real spend history but no budget envelope — this is where that
// history becomes useful instead of cluttering the Variable budget list
// with meaningless "Rp 0 left" rows. See budget/index.tsx and
// service.build_period_view()'s monthly_limit filter.
const PATTERNS_MONTHS = 12;

const PATTERN_LABELS: Record<CategoryPatternTag, string> = {
  new: "New",
  "one-off": "One-off",
  occasional: "Occasional",
  rising: "Rising",
  falling: "Falling",
  recurring: "Recurring",
};

// Text chips, not chart marks, so these draw from the validated status
// palette instead of the capped 2-slot categorical / 5-step sequential
// chart ramp — see tokens.ts's chart palette comment.
function patternTagColor(theme: Theme, tag: CategoryPatternTag): string {
  switch (tag) {
    case "rising":
      return theme.status.tight;
    case "falling":
      return theme.status.comfortable;
    case "recurring":
    case "occasional":
      return theme.colors.neutral[400];
    default:
      return theme.colors.neutral[500];
  }
}

export default function CategoryPatternsScreen() {
  const theme = useTheme();
  const { revision } = useBudgetRevision();

  const fetcher = useCallback(() => getCategoryPatterns(PATTERNS_MONTHS), []);
  const { data, loading, error, refetch } = useResource<CategoryPatterns>(fetcher, "Couldn't load category patterns.", revision);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Category patterns" />
      <ListScreen
        data={data}
        loading={loading}
        error={error}
        refetch={refetch}
        skeleton={
          <Stack p={4} gap={3}>
            <Skeleton height={80} radius={theme.radius.md} />
            <Skeleton height={80} radius={theme.radius.md} />
            <Skeleton height={80} radius={theme.radius.md} />
          </Stack>
        }
        isEmpty={(d) => d.categories.length === 0}
        emptyMessage="No category spend in this window yet."
        emptyIcon={Target}
      >
        {(patterns) => (
          <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[5], gap: theme.spacing[3] }}>
            <Stack gap={0.5}>
              <Text variant="title">Category patterns</Text>
              <Text variant="caption" tone="muted">
                Last {patterns.windowMonths} months · {formatRupiah(patterns.totalSpend)} total spend
              </Text>
            </Stack>

            <Stack gap={3}>
              {patterns.categories.map((c) => (
                <CategoryPatternRow key={c.categoryId ?? "uncategorized"} category={c} patterns={patterns} />
              ))}
            </Stack>

            {patterns.dormantCount > 0 ? (
              <Text variant="caption" tone="faint">
                {patterns.dormantCount} categor{patterns.dormantCount === 1 ? "y" : "ies"} with no activity in this window.
              </Text>
            ) : null}
          </ScrollView>
        )}
      </ListScreen>
    </SafeAreaView>
  );
}

function CategoryPatternRow({ category: c, patterns }: { category: CategoryPattern; patterns: CategoryPatterns }) {
  const theme = useTheme();
  const tagColor = patternTagColor(theme, c.pattern);
  const largestLabel = c.largestMonth ? monthLabelFor(patterns, c.largestMonth.month) : null;

  return (
    <ExpandableCard
      accessibilityLabel={`${c.name}, ${PATTERN_LABELS[c.pattern]}, expand for monthly detail`}
      header={() => (
        <Stack gap={1.5} style={{ flex: 1 }}>
          <HStack justify="space-between" align="center">
            <Text variant="label">{c.name}</Text>
            <Box py={0.5} px={1.5} radius="pill" bg={`${tagColor}26`} style={{ alignSelf: "flex-start" }}>
              <Text variant="caption" style={{ color: tagColor }}>
                {PATTERN_LABELS[c.pattern]}
              </Text>
            </Box>
          </HStack>
          <HStack justify="space-between" align="center">
            <Text variant="meta" tone="muted" numeric>
              {formatRupiahCompact(c.avgPerMonth)}/mo
            </Text>
            <Sparkline data={c.series} width={64} height={24} />
          </HStack>
        </Stack>
      )}
    >
      <Stack gap={3}>
        <ColumnChart
          data={c.series.map((value, i) => ({
            key: patterns.months[i],
            label: `${patterns.monthLabels[i]} ${patterns.months[i].slice(0, 4)}`,
            shortLabel: patterns.monthLabels[i],
            value,
            isPartial: i === c.series.length - 1,
          }))}
          height={110}
          baseline={c.avgPerMonth || undefined}
          baselineLabel="avg"
          formatValue={formatRupiah}
          formatAxisValue={formatRupiahCompact}
        />
        <HStack justify="space-between">
          <Text variant="caption" tone="muted">
            {c.monthsActive} of {c.monthsInWindow} months · {c.count} transaction{c.count === 1 ? "" : "s"}
          </Text>
          <Text variant="caption" tone="muted" numeric>
            {formatRupiah(c.total)} total
          </Text>
        </HStack>
        {c.largestMonth && largestLabel ? (
          <Text variant="caption" tone="muted">
            Biggest month: {largestLabel} · {formatRupiah(c.largestMonth.spend)}
          </Text>
        ) : null}
      </Stack>
    </ExpandableCard>
  );
}

function monthLabelFor(patterns: CategoryPatterns, monthKey: string): string | null {
  const i = patterns.months.indexOf(monthKey);
  return i === -1 ? null : `${patterns.monthLabels[i]} ${monthKey.slice(0, 4)}`;
}
