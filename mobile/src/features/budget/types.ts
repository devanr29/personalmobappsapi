// Ledger-side types for the standalone budget feature. BudgetSnapshot/
// BudgetStatusLevel stay in @/api/types since Home's HomeResponse and
// Chat's ChatBudgetData also depend on that exact shape.
import type { BudgetStatusLevel } from "@/api/types";

export type TransactionDirection = "expense" | "income" | "transfer" | "adjustment";

export interface Wallet {
  id: number;
  name: string;
  kind: string;
  openingBalance: number;
  spendable: boolean;
  isDefault: boolean;
  archived: boolean;
  balance: number;
}

export interface Category {
  id: number;
  name: string;
  kind: "fixed" | "variable";
  monthlyLimit: number | null;
  rollover: boolean;
  archived: boolean;
}

export interface Transaction {
  id: number;
  occurredAt: string;
  amount: number;
  direction: TransactionDirection;
  categoryId: number | null;
  categoryName: string | null;
  walletId: number | null;
  walletName: string | null;
  note: string | null;
  source: string;
  billId: number | null;
  goalId: number | null;
}

export interface TransactionsPage {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface BudgetLineItem {
  billId: number | null;
  name: string;
  amount: number;
  dueDay: number | null;
}

export interface BudgetVariableItem {
  categoryId: number | null;
  name: string;
  remaining: number;
  spent: number;
  overBudget: number;
  /** Marked paid this period (budget_category_payments) — remaining reads
   * as 0 regardless of actual spend once set, mirroring a paid bill's
   * still_owed exclusion. See VariableCategoryCard's "Mark as paid". */
  paid: boolean;
}

export interface BudgetUnmatchedItem {
  name: string;
  amount: number;
}

export interface TodayCard {
  date: string;
  spend: number;
  allowance: number;
  remainingToday: number;
  nextBill: { id: number; name: string; amount: number; dueDay: number; daysUntil: number } | null;
}

// GET /api/budget/breakdown — period-scoped compute_budget() view.
export interface BudgetBreakdown {
  remaining: number;
  stillOwed: BudgetLineItem[];
  pendingAmounts: BudgetLineItem[];
  remainingVar: BudgetVariableItem[];
  unmatchedSpending: BudgetUnmatchedItem[];
  totalStillOwed: number;
  totalVarRemaining: number;
  totalDeductions: number;
  freeMoney: number;
  dailyBudget: number;
  daysLeft: number;
  statusLevel: BudgetStatusLevel;
  today: TodayCard | null;
  // Folded in so the Budget screen's initial load is one request instead
  // of four (GET /breakdown used to be joined by separate GET /api/budget,
  // /wallets, /alerts calls).
  wallets: Wallet[];
  computedAt: string;
  unreadAlertCount: number;
}

export interface Bill {
  id: number;
  name: string;
  amount: number;
  dueDay: number | null;
  cadence: string;
  active: boolean;
  categoryId: number | null;
  walletId: number | null;
  autopost: boolean;
}

export interface SetupStatus {
  seeded: boolean;
  walletCount: number;
  categoryCount: number;
  billCount: number;
}

export interface SetupResult {
  wallets: Wallet[];
  categories: Category[];
  bills: Bill[];
  periodId: number;
  openingBalance: number;
}

export interface SetupWalletInput {
  name: string;
  kind?: string;
  openingBalance?: number;
  spendable?: boolean;
  isDefault?: boolean;
}

export interface SetupCategoryInput {
  name: string;
  kind: "fixed" | "variable";
  monthlyLimit?: number | null;
}

export interface SetupBillInput {
  name: string;
  amount: number;
  dueDay?: number | null;
  categoryName?: string;
}

export interface SetupInput {
  payrollDay?: number;
  wallets: SetupWalletInput[];
  categories: SetupCategoryInput[];
  bills: SetupBillInput[];
  force?: boolean;
}

// ================================================================
// INSIGHTS — GET /api/budget/insights and /insights/history
// ================================================================
export interface InsightsPeriod {
  id: number;
  startDate: string;
  endDate: string;
  label: string;
  totalDays: number;
  elapsedDays: number;
  daysLeft: number;
  payrollDay: number;
}

export interface DailyPoint {
  date: string;
  spend: number;
  variableSpend: number;
  income: number;
  count: number;
}

export interface PacePoint {
  date: string;
  actual: number;
  ideal: number;
}

export interface PaceData {
  envelope: number;
  idealPerDay: number;
  points: PacePoint[];
  aheadBy: number;
}

export interface CategorySpend {
  categoryId: number | null;
  name: string;
  kind: "fixed" | "variable" | null;
  spend: number;
  count: number;
  limit: number | null;
  share: number;
}

export interface CategoryTopItem {
  categoryId: number | null;
  name: string;
  spend: number;
  count: number;
  isOther: boolean;
}

export interface BudgetVsActual {
  categoryId: number;
  name: string;
  budget: number;
  actual: number;
  remaining: number;
  overBudget: number;
  pct: number;
}

export interface InsightsStats {
  moneyInHand: number;
  totalStillOwed: number;
  freeMoney: number;
  dailyBudget: number;
  statusLevel: BudgetStatusLevel;
  spendToDate: number;
  avgDailySpend: number;
  projectedRemainingSpend: number;
  projectedEndBalance: number;
  burnRateVsIdeal: number;
  largestExpense: { id: number; name: string; amount: number; occurredAt: string } | null;
  spendSparkline: number[];
  todayAllowance: number;
  todayRemaining: number;
}

export interface HeatmapCellData {
  date: string;
  label: string;
  weekday: number;
  spend: number;
  count: number;
}

export interface HeatmapPayload {
  cells: HeatmapCellData[];
  maxSpend: number;
  maxCount: number;
}

export interface WalletCompositionItem {
  id: number;
  name: string;
  kind: string;
  spendable: boolean;
  balance: number;
  share: number;
}

export interface WalletComposition {
  items: WalletCompositionItem[];
  total: number;
  spendableTotal: number;
}

export interface BudgetInsights {
  period: InsightsPeriod;
  daily: DailyPoint[];
  pace: PaceData;
  categories: CategorySpend[];
  categoriesTop: CategoryTopItem[];
  budgetVsActual: BudgetVsActual[];
  stats: InsightsStats;
  heatmap: HeatmapPayload;
  wallets: WalletComposition;
}

export interface HistoryPeriod {
  periodId: number | null;
  startDate: string | null;
  endDate: string | null;
  label: string;
  /** Axis tick for the column chart, e.g. "Jul". */
  shortLabel: string;
  /** "YYYY-MM" in month mode, null in period mode. */
  monthKey: string | null;
  spend: number;
  income: number;
  net: number;
  count: number;
  isCurrent: boolean;
}

export interface BudgetHistory {
  periods: HistoryPeriod[];
  spendTrend: number[];
  incomeTrend: number[];
  deltaVsPrevious: { spend: number; spendPct: number; isPartial: boolean } | null;
  averageSpend: number;
}

export type CategoryPatternTag = "new" | "one-off" | "occasional" | "rising" | "falling" | "recurring";

export interface CategoryPattern {
  categoryId: number | null;
  name: string;
  kind: "fixed" | "variable" | null;
  monthlyLimit: number | null;
  total: number;
  count: number;
  avgPerMonth: number;
  avgPerActiveMonth: number;
  monthsActive: number;
  monthsInWindow: number;
  share: number;
  pattern: CategoryPatternTag;
  largestMonth: { month: string; spend: number } | null;
  /** Dense, length === CategoryPatterns.months.length. Last entry is the
   * current, still-accruing month — included for the chart, excluded from
   * every stat above. */
  series: number[];
}

export interface CategoryPatterns {
  /** Shared x-axis for every category's series, "YYYY-MM", oldest first. */
  months: string[];
  monthLabels: string[];
  windowMonths: number;
  completeMonths: number;
  currentMonth: string;
  totalSpend: number;
  /** Categories with zero spend anywhere in the window — counted, not listed. */
  dormantCount: number;
  categories: CategoryPattern[];
}

// ================================================================
// GOALS
// ================================================================
export type GoalKind = "sinking" | "debt" | "emergency";

export interface Goal {
  id: number;
  name: string;
  kind: GoalKind;
  targetAmount: number;
  targetDate: string | null;
  monthlyContribution: number | null;
  reserveFromFree: boolean;
  walletId: number | null;
  archived: boolean;
  saved: number;
}

// ================================================================
// ALERTS
// ================================================================
export type AlertKind = "daily_checkin" | "bill_due" | "over_budget" | "low_daily_budget" | "period_rollover";

export interface Alert {
  id: number;
  kind: AlertKind;
  title: string;
  body: string;
  sentAt: string;
  delivered: boolean;
  readAt: string | null;
}

export interface AlertPrefs {
  dailyCheckinEnabled: boolean;
  dailyCheckinTime: string;
  billDueLeadDays: number;
  overBudgetEnabled: boolean;
  overBudgetThresholdPct: number;
  lowDailyBudgetThreshold: number;
}

// ================================================================
// WALLET SYNC — two-way sync against Wallet by BudgetBakers. Mirrors
// features/budget/wallet/sync.py's return shapes (already camelCase-keyed
// on the backend, no snake_case translation needed here).
// ================================================================
export interface WalletSyncSkip {
  remoteId?: string;
  localId?: number;
  name?: string;
  reason: string;
}

export interface WalletSyncEntityResult {
  created: number;
  updated?: number;
  deleted?: number;
  skipped: WalletSyncSkip[];
  errors?: { localId?: number; localIds?: number[]; reason: string }[];
  // Records pull only: the server bounded this call to a time budget and
  // stopped at a page boundary — more history remains. pullWalletSync()
  // keeps calling until this is false.
  hasMore?: boolean;
}

export interface WalletPullSummary {
  accounts: WalletSyncEntityResult;
  categories: WalletSyncEntityResult;
  labels: WalletSyncEntityResult;
  goals: WalletSyncEntityResult;
  bills: WalletSyncEntityResult;
  records: WalletSyncEntityResult;
}

export interface WalletPushSummary {
  wallets: WalletSyncEntityResult;
  categories: WalletSyncEntityResult;
  labels: WalletSyncEntityResult;
  records: WalletSyncEntityResult;
}

export interface WalletSyncStatus {
  configured: boolean;
  cursors: Record<string, string>;
  lastRun: { at: string; summary: Record<string, unknown> } | null;
  tokenExpiresAt: string | null;
  rateLimitLimit: number | null;
  rateLimitRemaining: number | null;
  linkCounts: Record<string, number>;
  error: string | null;
}

export interface WalletSyncPreview {
  pull: WalletPullSummary;
  push: WalletPushSummary;
}

export interface WalletSyncCompare {
  local: { freeMoney: number; dailyBudget: number; daysLeft: number; statusLevel: BudgetStatusLevel } | null;
  walletBudgets: { id: string; name: string; spending: unknown }[];
  note: string;
}
