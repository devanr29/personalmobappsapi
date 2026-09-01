import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Plus, Receipt } from "phosphor-react-native";
import { ActivityIndicator, Pressable, ScrollView, SectionList } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FAB } from "@/components/FAB";
import { IconBadge } from "@/components/IconBadge";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { SwipeableRow } from "@/components/SwipeableRow";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { deleteTransaction, listCategories, listTransactions, listWallets } from "@/features/budget/api";
import { TransactionSheet } from "@/features/budget/components/TransactionSheet";
import type { Category, Transaction, TransactionDirection, Wallet } from "@/features/budget/types";
import { budgetDayKey, formatBudgetDayHeader, formatBudgetTime } from "@/features/budget/utils/budgetDate";
import { usePagedResource } from "@/hooks/usePagedResource";
import { AnimatedListItem, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text, type Tone } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";

const PAGE_SIZE = 30;

type DayGroup = { title: string; key: string; data: Transaction[] };

function groupByDay(items: Transaction[]): DayGroup[] {
  const groups: DayGroup[] = [];
  const byKey = new Map<string, DayGroup>();
  for (const txn of items) {
    const key = budgetDayKey(txn.occurredAt);
    let group = byKey.get(key);
    if (!group) {
      group = { key, title: formatBudgetDayHeader(txn.occurredAt), data: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.data.push(txn);
  }
  return groups;
}

const DIRECTION_FILTERS: { value: TransactionDirection | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
];

export default function TransactionsScreen() {
  const theme = useTheme();
  const { revision, invalidate } = useBudgetRevision();
  const [addSheetVisible, setAddSheetVisible] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

  const [categories, setCategories] = useState<Category[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<number | null>(null);
  const [walletFilter, setWalletFilter] = useState<number | null>(null);
  const [directionFilter, setDirectionFilter] = useState<TransactionDirection | "all">("all");

  useEffect(() => {
    listCategories().then(setCategories).catch(() => {});
    listWallets().then(setWallets).catch(() => {});
  }, []);

  const fetchPage = useCallback(
    (offset: number) =>
      listTransactions({
        limit: PAGE_SIZE,
        offset,
        categoryId: categoryFilter ?? undefined,
        walletId: walletFilter ?? undefined,
        direction: directionFilter === "all" ? undefined : directionFilter,
      }),
    [categoryFilter, walletFilter, directionFilter],
  );
  const { items, total, hasMore, loading, loadingMore, error, refetch, loadMore, mutateItems } = usePagedResource<Transaction>(
    fetchPage,
    "Couldn't load transactions.",
    revision,
  );

  const sections = useMemo(() => groupByDay(items), [items]);

  const handleDelete = (txn: Transaction) => {
    mutateItems(
      (prev) => prev.filter((t) => t.id !== txn.id),
      (prev) => [...prev, txn].sort((a, b) => (a.occurredAt < b.occurredAt ? 1 : -1)),
      async () => {
        await deleteTransaction(txn.id);
        invalidate();
      },
    );
  };

  const handleSaved = () => {
    invalidate();
    refetch();
  };

  const openEdit = (txn: Transaction) => {
    setEditingTransaction(txn);
    setAddSheetVisible(true);
  };

  const openCreate = () => {
    setEditingTransaction(null);
    setAddSheetVisible(true);
  };

  const hasFilters = categoryFilter !== null || walletFilter !== null || directionFilter !== "all";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Transactions" />

      <Stack py={2} gap={2}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: theme.spacing[4], gap: theme.spacing[2] }}>
          <HStack gap={2}>
            {DIRECTION_FILTERS.map((f) => (
              <FilterChip key={f.value} label={f.label} selected={directionFilter === f.value} onPress={() => setDirectionFilter(f.value)} />
            ))}
          </HStack>
        </ScrollView>
        {categories.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: theme.spacing[4], gap: theme.spacing[2] }}>
            <HStack gap={2}>
              <FilterChip label="All categories" selected={categoryFilter === null} onPress={() => setCategoryFilter(null)} />
              {categories.map((c) => (
                <FilterChip key={c.id} label={c.name} selected={categoryFilter === c.id} onPress={() => setCategoryFilter(c.id)} />
              ))}
            </HStack>
          </ScrollView>
        ) : null}
        {wallets.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: theme.spacing[4], gap: theme.spacing[2] }}>
            <HStack gap={2}>
              <FilterChip label="All wallets" selected={walletFilter === null} onPress={() => setWalletFilter(null)} />
              {wallets.map((w) => (
                <FilterChip key={w.id} label={w.name} selected={walletFilter === w.id} onPress={() => setWalletFilter(w.id)} />
              ))}
            </HStack>
          </ScrollView>
        ) : null}
        {!loading && total > 0 ? (
          <Text variant="caption" tone="muted" style={{ paddingHorizontal: theme.spacing[4] }}>
            {total} transaction{total === 1 ? "" : "s"}
          </Text>
        ) : null}
      </Stack>

      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={56} radius={theme.radius.md} />
          <Skeleton height={56} radius={theme.radius.md} />
          <Skeleton height={56} radius={theme.radius.md} />
        </Stack>
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : items.length === 0 ? (
        <EmptyState
          message={hasFilters ? "No transactions match these filters." : "No transactions yet. Tap + to add one."}
          IconComponent={Receipt}
        />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[2], gap: theme.spacing[2] }}
          stickySectionHeadersEnabled={false}
          onEndReached={loadMore}
          onEndReachedThreshold={0.4}
          renderSectionHeader={({ section }) => (
            <Text variant="label" tone="muted" style={{ paddingTop: theme.spacing[3], paddingBottom: theme.spacing[1] }}>
              {section.title}
            </Text>
          )}
          renderItem={({ item, index }) => (
            <AnimatedListItem index={index % 8}>
              <SwipeableRow onDelete={() => handleDelete(item)}>
                <PressableScale onPress={() => openEdit(item)}>
                  <Card padding={0}>
                    <TransactionRow txn={item} />
                  </Card>
                </PressableScale>
              </SwipeableRow>
            </AnimatedListItem>
          )}
          ItemSeparatorComponent={() => <Stack style={{ height: theme.spacing[2] }} />}
          ListFooterComponent={
            loadingMore ? (
              <Stack py={4} align="center">
                <ActivityIndicator size="small" color={theme.colors.accent} />
              </Stack>
            ) : !hasMore && items.length > 0 ? (
              <Stack py={4} align="center">
                <Text variant="caption" tone="faint">
                  That&rsquo;s everything
                </Text>
              </Stack>
            ) : null
          }
        />
      )}

      <FAB IconComponent={Plus} onPress={openCreate} accessibilityLabel="Add transaction" />
      <TransactionSheet
        visible={addSheetVisible}
        onClose={() => setAddSheetVisible(false)}
        onSaved={handleSaved}
        editingTransaction={editingTransaction}
      />
    </SafeAreaView>
  );
}

function FilterChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const theme = useTheme();
  const tone: Tone = selected ? "accent" : "secondary";

  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
      <Stack
        py={1.5}
        px={3}
        radius="pill"
        bg={selected ? theme.colors.accentRamp[900] : theme.colors.neutral[800]}
        style={{ borderWidth: 1, borderColor: selected ? theme.colors.accentRamp[700] : "transparent" }}
      >
        <Text variant="label" tone={tone}>
          {label}
        </Text>
      </Stack>
    </Pressable>
  );
}

function TransactionRow({ txn }: { txn: Transaction }) {
  const theme = useTheme();
  const isExpense = txn.direction === "expense";
  const sign = isExpense ? "-" : txn.direction === "income" ? "+" : "";

  return (
    <HStack align="center" gap={3} py={3} px={4}>
      <IconBadge
        IconComponent={isExpense ? ArrowUpRight : ArrowDownLeft}
        tone={isExpense ? "neutral" : "positive"}
        size={32}
      />
      <Stack flex={1} gap={0.5}>
        <Text variant="body">{txn.note || txn.categoryName || "Transaction"}</Text>
        <Text variant="caption" tone="faint">
          {[txn.categoryName, txn.walletName, formatBudgetTime(txn.occurredAt)].filter(Boolean).join(" · ")}
        </Text>
      </Stack>
      <Text
        variant="body"
        tone={isExpense ? "primary" : "positive"}
        numeric
        style={{ color: isExpense ? theme.colors.neutral[300] : theme.status.comfortable }}
      >
        {sign}
        {formatRupiah(txn.amount)}
      </Text>
    </HStack>
  );
}
