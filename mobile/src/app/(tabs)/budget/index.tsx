import { useCallback, useState } from "react";
import { useRouter } from "expo-router";
import { Bell, CheckCircle, Info, Plus, Sun, WarningCircle, XCircle, type Icon } from "phosphor-react-native";
import { ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AnimatedCurrency } from "@/components/AnimatedCurrency";
import { Card } from "@/components/Card";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { FAB } from "@/components/FAB";
import { Meter, StackedBar, clamp01 } from "@/components/charts";
import { ListScreen } from "@/components/ListScreen";
import { Skeleton } from "@/components/Skeleton";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import {
  createTransaction, getBreakdown, listBills, listCategories, payBill, payCategory, snapshotFromBreakdown, unpayBill, unpayCategory,
} from "@/features/budget/api";
import { AttachTransactionSheet, type AttachTarget } from "@/features/budget/components/AttachTransactionSheet";
import { BudgetItemSheet } from "@/features/budget/components/BudgetItemSheet";
import { FixedBudgetCard } from "@/features/budget/components/FixedBudgetCard";
import { TransactionSheet } from "@/features/budget/components/TransactionSheet";
import { VariableCategoryCard } from "@/features/budget/components/VariableCategoryCard";
import type { Bill, BudgetBreakdown, Category, TodayCard as TodayCardData, Wallet } from "@/features/budget/types";
import { useResource } from "@/hooks/useResource";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import type { BudgetSnapshot, BudgetStatusLevel } from "@/api/types";

// A single GET /breakdown carries the summary, wallet balances, and unread
// alert count together (see features/budget/serializers.py's
// camel_budget_breakdown) — this screen used to fire 4 parallel requests
// (getSummary + getBreakdown + listWallets + listAlerts), which meant the
// backend computed the ~9-query build_period_view() aggregate twice per
// screen load. Bills/categories are two extra small requests — they carry
// the ids and editable fields (amount/monthlyLimit) that the breakdown's
// serialized line items intentionally don't (see serializers.py), needed
// for the Fixed/Variable budget sections' edit sheets.
type OverviewResource = {
  breakdown: BudgetBreakdown | null;
  bills: Bill[];
  categories: Category[];
};

const STATUS_ICON: Record<BudgetStatusLevel, Icon> = {
  comfortable: CheckCircle,
  manageable: Info,
  tight: WarningCircle,
  short: XCircle,
};

const STATUS_LABEL: Record<BudgetStatusLevel, string> = {
  comfortable: "Comfortable",
  manageable: "Manageable",
  tight: "Tight",
  short: "Short",
};

export default function BudgetOverviewScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { revision, invalidate } = useBudgetRevision();
  const [addSheetVisible, setAddSheetVisible] = useState(false);
  const [budgetSheet, setBudgetSheet] = useState<{ itemKind: "category" | "bill"; editing: Category | Bill | null } | null>(null);
  const [payPendingBillId, setPayPendingBillId] = useState<number | null>(null);
  const [payPendingCategoryId, setPayPendingCategoryId] = useState<number | null>(null);
  const [attachTarget, setAttachTarget] = useState<AttachTarget | null>(null);

  const fetcher = useCallback(async (): Promise<OverviewResource> => {
    const [breakdown, bills, categories] = await Promise.all([getBreakdown(), listBills(), listCategories("variable")]);
    return { breakdown, bills, categories };
  }, []);
  const { data, loading, error, refetch } = useResource<OverviewResource>(fetcher, "Couldn't load your budget.", revision);

  const handleSaved = () => {
    invalidate();
    refetch();
  };

  const handleTogglePaid = async (bill: Bill, paidThisPeriod: boolean) => {
    setPayPendingBillId(bill.id);
    try {
      if (paidThisPeriod) {
        await unpayBill(bill.id);
      } else {
        await payBill(bill.id);
      }
      handleSaved();
    } catch {
      // No per-card error slot to surface this in — the card just stays in
      // its last known-good (unchanged) state on failure.
    } finally {
      setPayPendingBillId(null);
    }
  };

  const handleLogSpend = async (categoryId: number, amount: number, walletId: number) => {
    await createTransaction({ amount, direction: "expense", categoryId, walletId });
    handleSaved();
  };

  const handlePayAmount = async (bill: Bill, amount: number, walletId: number) => {
    await payBill(bill.id, { amount, walletId });
    handleSaved();
  };

  const handleToggleCategoryPaid = async (categoryId: number, paid: boolean) => {
    setPayPendingCategoryId(categoryId);
    try {
      if (paid) {
        await unpayCategory(categoryId);
      } else {
        await payCategory(categoryId);
      }
      handleSaved();
    } catch {
      // No per-card error slot to surface this in — the card just stays in
      // its last known-good (unchanged) state on failure.
    } finally {
      setPayPendingCategoryId(null);
    }
  };

  const handlePayCategoryAmount = async (categoryId: number, amount: number, walletId: number, createTransactionFlag: boolean) => {
    await payCategory(categoryId, { amount, walletId, createTransaction: createTransactionFlag });
    handleSaved();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ListScreen
        data={data}
        loading={loading}
        error={error}
        refetch={refetch}
        skeleton={
          <Stack p={4} gap={4}>
            <Skeleton height={150} radius={theme.radius.md} />
            <Skeleton height={80} radius={theme.radius.md} />
            <Skeleton height={140} radius={theme.radius.md} />
          </Stack>
        }
      >
        {({ breakdown, bills, categories }) => {
          const summary = breakdown ? snapshotFromBreakdown(breakdown) : null;
          const wallets = breakdown?.wallets ?? [];
          const unreadAlerts = breakdown?.unreadAlertCount ?? 0;
          const categoryById = new Map(categories.map((c) => [c.id, c]));
          const stillOwedBillIds = new Set((breakdown?.stillOwed ?? []).map((e) => e.billId).filter((id): id is number => id != null));
          return (
          <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[5], gap: theme.spacing[4] }}>
            <HStack align="center" justify="space-between">
              <Text variant="title">Budget</Text>
              <PressableScale
                onPress={() => router.push("/budget/alerts")}
                accessibilityRole="button"
                accessibilityLabel={unreadAlerts > 0 ? `Alerts, ${unreadAlerts} unread` : "Alerts"}
              >
                <View>
                  <Bell size={20} color={theme.colors.text} />
                  {unreadAlerts > 0 ? (
                    <View
                      style={{
                        position: "absolute", top: -2, right: -2, width: 8, height: 8,
                        borderRadius: theme.radius.full, backgroundColor: theme.status.short,
                      }}
                    />
                  ) : null}
                </View>
              </PressableScale>
            </HStack>

            <HStack gap={4}>
              <PressableScale
                onPress={() => router.push("/budget/insights")}
                accessibilityRole="button"
                accessibilityLabel="See budget insights"
              >
                <Text variant="meta" tone="accent">
                  Insights
                </Text>
              </PressableScale>
              <PressableScale
                onPress={() => router.push("/budget/goals")}
                accessibilityRole="button"
                accessibilityLabel="See savings goals"
              >
                <Text variant="meta" tone="accent">
                  Goals
                </Text>
              </PressableScale>
              <PressableScale
                onPress={() => router.push("/budget/transactions")}
                accessibilityRole="button"
                accessibilityLabel="See all transactions"
              >
                <Text variant="meta" tone="accent">
                  Transactions
                </Text>
              </PressableScale>
              <PressableScale
                onPress={() => router.push("/budget/sync")}
                accessibilityRole="button"
                accessibilityLabel="Wallet sync"
              >
                <Text variant="meta" tone="accent">
                  Sync
                </Text>
              </PressableScale>
            </HStack>

            {!summary ? (
              <Card>
                <Stack gap={2}>
                  <Text variant="cardTitle">No budget set up yet</Text>
                  <Text variant="label" tone="muted">
                    Wallets and categories haven&rsquo;t been configured yet.
                  </Text>
                  <PressableScale
                    onPress={() => router.push("/budget/setup")}
                    accessibilityRole="button"
                    accessibilityLabel="Set up budget"
                  >
                    <Text variant="meta" tone="accent" style={{ fontFamily: theme.fontFamily.medium }}>
                      Set up budget →
                    </Text>
                  </PressableScale>
                </Stack>
              </Card>
            ) : (
              <>
                {breakdown?.today ? <TodayCard today={breakdown.today} /> : null}

                <DailyBudgetHero summary={summary} />

                {wallets.length > 0 ? <WalletStrip wallets={wallets} /> : null}

                {breakdown ? <Composition breakdown={breakdown} /> : null}

                <CollapsibleSection
                  title="Fixed budget"
                  summary={fixedSummary(bills, stillOwedBillIds)}
                  addLabel="Add fixed budget"
                  onAdd={() => setBudgetSheet({ itemKind: "bill", editing: null })}
                >
                  {bills.map((bill) => (
                    <FixedBudgetCard
                      key={bill.id}
                      bill={bill}
                      paidThisPeriod={!stillOwedBillIds.has(bill.id)}
                      payPending={payPendingBillId === bill.id}
                      wallets={wallets}
                      onEdit={() => setBudgetSheet({ itemKind: "bill", editing: bill })}
                      onTogglePaid={() => handleTogglePaid(bill, !stillOwedBillIds.has(bill.id))}
                      onPayAmount={(amount, walletId) => handlePayAmount(bill, amount, walletId)}
                      onAttachTransaction={() => setAttachTarget({ kind: "bill", id: bill.id, name: bill.name })}
                    />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Variable budget"
                  summary={variableSummary(breakdown)}
                  addLabel="Add variable budget"
                  onAdd={() => setBudgetSheet({ itemKind: "category", editing: null })}
                >
                  {(breakdown?.remainingVar ?? []).length === 0 ? (
                    <Text variant="label" tone="muted">
                      No variable budgets yet — add one below.
                    </Text>
                  ) : (
                    (breakdown?.remainingVar ?? []).map((item) => (
                      <VariableCategoryCard
                        key={item.categoryId ?? item.name}
                        item={item}
                        category={item.categoryId != null ? categoryById.get(item.categoryId) : undefined}
                        wallets={wallets}
                        payPending={payPendingCategoryId === item.categoryId}
                        onEdit={() => {
                          const category = item.categoryId != null ? categoryById.get(item.categoryId) : undefined;
                          if (category) setBudgetSheet({ itemKind: "category", editing: category });
                        }}
                        onLogSpend={(amount, walletId) => handleLogSpend(item.categoryId as number, amount, walletId)}
                        onAttachTransaction={() => setAttachTarget({ kind: "category", id: item.categoryId as number, name: item.name })}
                        onTogglePaid={() => handleToggleCategoryPaid(item.categoryId as number, item.paid)}
                        onPayAmount={(amount, walletId, createTransactionFlag) =>
                          handlePayCategoryAmount(item.categoryId as number, amount, walletId, createTransactionFlag)
                        }
                      />
                    ))
                  )}
                </CollapsibleSection>
              </>
            )}
          </ScrollView>
          );
        }}
      </ListScreen>
      <FAB IconComponent={Plus} onPress={() => setAddSheetVisible(true)} accessibilityLabel="Add transaction" />
      <TransactionSheet visible={addSheetVisible} onClose={() => setAddSheetVisible(false)} onSaved={handleSaved} />
      <BudgetItemSheet
        visible={budgetSheet !== null}
        onClose={() => setBudgetSheet(null)}
        onSaved={handleSaved}
        itemKind={budgetSheet?.itemKind ?? "category"}
        editing={budgetSheet?.editing}
      />
      <AttachTransactionSheet
        visible={attachTarget !== null}
        onClose={() => setAttachTarget(null)}
        onAttached={handleSaved}
        target={attachTarget ?? { kind: "category", id: 0, name: "" }}
      />
    </SafeAreaView>
  );
}

function fixedSummary(bills: Bill[], stillOwedBillIds: Set<number>): string {
  const total = bills.reduce((sum, b) => sum + b.amount, 0);
  const unpaidCount = bills.filter((b) => stillOwedBillIds.has(b.id)).length;
  const base = `${bills.length} item${bills.length === 1 ? "" : "s"} · ${formatRupiah(total)}`;
  return unpaidCount > 0 ? `${base} · ${unpaidCount} unpaid` : base;
}

function variableSummary(breakdown: BudgetBreakdown | null): string {
  const items = breakdown?.remainingVar ?? [];
  const left = breakdown?.totalVarRemaining ?? 0;
  return `${items.length} item${items.length === 1 ? "" : "s"} · ${formatRupiah(left)} left`;
}

function TodayCard({ today }: { today: TodayCardData }) {
  const theme = useTheme();
  const allowance = today.allowance;
  const progress = allowance > 0 ? clamp01(today.spend / allowance) : 0;
  const isOver = today.remainingToday < 0;

  return (
    <Card>
      <Stack gap={3}>
        <HStack align="center" gap={1.5}>
          <Sun size={16} color={theme.colors.accent} weight="fill" />
          <Text variant="label" tone="secondary">
            Today
          </Text>
        </HStack>
        <HStack align="baseline" justify="space-between">
          <HStack align="baseline" gap={1.5}>
            <AnimatedCurrency value={Math.abs(today.remainingToday)} variant="title" tone={isOver ? "negative" : "primary"} />
            <Text variant="caption" tone="muted">
              {isOver ? "over today" : "left today"}
            </Text>
          </HStack>
          <Text variant="caption" tone="muted" numeric>
            Spent {formatRupiah(today.spend)}
          </Text>
        </HStack>
        <Meter value={progress} color={isOver ? theme.status.short : theme.colors.accent} />
        {today.nextBill ? (
          <Text variant="caption" tone="faint">
            {today.nextBill.name} ({formatRupiah(today.nextBill.amount)}) due in {today.nextBill.daysUntil} day
            {today.nextBill.daysUntil === 1 ? "" : "s"}
          </Text>
        ) : null}
      </Stack>
    </Card>
  );
}

function DailyBudgetHero({ summary }: { summary: BudgetSnapshot }) {
  const theme = useTheme();
  const StatusIcon = STATUS_ICON[summary.statusLevel];
  const statusColor = theme.status[summary.statusLevel];
  const progress = summary.remaining > 0 ? clamp01(summary.free / summary.remaining) : 0;

  return (
    <Card>
      <Stack gap={3}>
        <HStack align="center" justify="space-between">
          <HStack align="center" gap={1.5}>
            <StatusIcon size={16} weight="fill" color={statusColor} />
            <Text variant="label" style={{ color: statusColor }}>
              {STATUS_LABEL[summary.statusLevel]}
            </Text>
          </HStack>
          <Text variant="caption" tone="muted">
            {summary.daysToPayday} days to payday
          </Text>
        </HStack>
        <HStack align="baseline" gap={1.5}>
          <AnimatedCurrency value={summary.dailyBudget} variant="display" />
          <Text variant="body" tone="muted">
            /day
          </Text>
        </HStack>
        <Meter value={progress} color={statusColor} />
        <HStack justify="space-between">
          <Text variant="caption" tone="muted" numeric>
            Left {formatRupiah(summary.free)}
          </Text>
          <Text variant="caption" tone="muted" numeric>
            of {formatRupiah(summary.remaining)}
          </Text>
        </HStack>
      </Stack>
    </Card>
  );
}

function WalletStrip({ wallets }: { wallets: Wallet[] }) {
  const theme = useTheme();
  return (
    <Card>
      <Stack gap={3}>
        <Text variant="heading">Wallets</Text>
        <Stack gap={2}>
          {wallets.map((w) => (
            <HStack key={w.id} align="center" justify="space-between">
              <Text variant="label" tone="secondary">
                {w.name}
              </Text>
              <Text variant="bodyStrong" numeric style={{ color: w.balance < 0 ? theme.status.short : theme.colors.text }}>
                {formatRupiah(w.balance)}
              </Text>
            </HStack>
          ))}
        </Stack>
      </Stack>
    </Card>
  );
}

function Composition({ breakdown }: { breakdown: BudgetBreakdown }) {
  const theme = useTheme();
  const [accent, amber] = theme.chart.categorical;

  return (
    <Card>
      <Stack gap={3}>
        <Text variant="heading">Where it&rsquo;s going</Text>
        <StackedBar
          segments={[
            { value: Math.max(0, breakdown.freeMoney), color: accent },
            { value: Math.max(0, breakdown.totalDeductions), color: amber },
          ]}
          total={breakdown.remaining}
        />
        <HStack gap={4}>
          <LegendSwatch color={accent} label="Free" amount={breakdown.freeMoney} />
          <LegendSwatch color={amber} label="Deductions" amount={breakdown.totalDeductions} />
        </HStack>
      </Stack>
    </Card>
  );
}

function LegendSwatch({ color, label, amount }: { color: string; label: string; amount: number }) {
  const theme = useTheme();
  return (
    <HStack align="center" gap={1.5} style={{ flex: 1 }}>
      <View style={{ width: 8, height: 8, borderRadius: theme.radius.full, backgroundColor: color }} />
      <Stack>
        <Text variant="caption" tone="muted">
          {label}
        </Text>
        <Text variant="meta" numeric>
          {formatRupiah(amount)}
        </Text>
      </Stack>
    </HStack>
  );
}

