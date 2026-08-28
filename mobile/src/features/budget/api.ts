import { apiClient } from "@/api/client";
import type { BudgetSnapshot } from "@/api/types";
import type {
  Alert,
  AlertPrefs,
  Bill,
  BudgetBreakdown,
  BudgetHistory,
  BudgetInsights,
  Category,
  CategoryPatterns,
  Goal,
  GoalKind,
  SetupInput,
  SetupResult,
  SetupStatus,
  Transaction,
  TransactionDirection,
  TransactionsPage,
  Wallet,
  WalletPullSummary,
  WalletPushSummary,
  WalletSyncCompare,
  WalletSyncPreview,
  WalletSyncStatus,
} from "./types";

export function getSummary() {
  return apiClient.get<BudgetSnapshot | null>("/api/budget");
}

export function getBreakdown() {
  return apiClient.get<BudgetBreakdown | null>("/api/budget/breakdown");
}

// GET /breakdown already carries every field a BudgetSnapshot needs (see
// features/budget/serializers.py's camel_budget_breakdown) — this derives
// one client-side instead of the screen also firing GET /api/budget, which
// would recompute the same ~9-query build_period_view() a second time.
export function snapshotFromBreakdown(breakdown: BudgetBreakdown): BudgetSnapshot {
  return {
    remaining: breakdown.remaining,
    deductions: breakdown.totalDeductions,
    free: breakdown.freeMoney,
    dailyBudget: breakdown.dailyBudget,
    daysToPayday: breakdown.daysLeft,
    statusLevel: breakdown.statusLevel,
    computedAt: breakdown.computedAt,
  };
}

export function getInsights() {
  return apiClient.get<BudgetInsights | null>("/api/budget/insights");
}

export function getInsightsHistory(periods = 6, groupBy: "period" | "month" = "period") {
  return apiClient.get<BudgetHistory>(`/api/budget/insights/history?periods=${periods}&groupBy=${groupBy}`);
}

export function getCategoryPatterns(months = 12) {
  return apiClient.get<CategoryPatterns>(`/api/budget/insights/categories?months=${months}`);
}

export function listWallets(includeArchived = false) {
  const qs = includeArchived ? "?includeArchived=1" : "";
  return apiClient.get<{ items: Wallet[] }>(`/api/budget/wallets${qs}`).then((r) => r.items);
}

export function createWallet(input: {
  name: string;
  kind?: string;
  openingBalance?: number;
  spendable?: boolean;
  isDefault?: boolean;
}) {
  return apiClient.post<{ wallet: Wallet }>("/api/budget/wallets", input).then((r) => r.wallet);
}

export type UpdateWalletInput = Partial<{
  name: string;
  kind: string;
  openingBalance: number;
  spendable: boolean;
  isDefault: boolean;
  archived: boolean;
}>;

export function updateWallet(id: number, input: UpdateWalletInput) {
  return apiClient.patch<{ wallet: Wallet }>(`/api/budget/wallets/${id}`, input).then((r) => r.wallet);
}

export function deleteWallet(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean }>(`/api/budget/wallets/${id}`);
}

export function transferBetweenWallets(input: {
  fromWalletId: number;
  toWalletId: number;
  amount: number;
  occurredAt?: string;
  note?: string;
}) {
  return apiClient.post<{ transaction: Transaction; summary: BudgetSnapshot | null }>(
    "/api/budget/wallets/transfer",
    input,
  );
}

export function reconcileWallet(id: number, actualBalance: number, note?: string) {
  return apiClient.post<{ adjusted: boolean; delta: number; summary: BudgetSnapshot | null }>(
    `/api/budget/wallets/${id}/reconcile`,
    { actualBalance, note },
  );
}

export function listCategories(kind?: "fixed" | "variable", includeArchived = false) {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (includeArchived) params.set("includeArchived", "1");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiClient.get<{ items: Category[] }>(`/api/budget/categories${qs}`).then((r) => r.items);
}

export function createCategory(input: {
  name: string;
  kind: "fixed" | "variable";
  monthlyLimit?: number | null;
  rollover?: boolean;
}) {
  return apiClient.post<{ category: Category }>("/api/budget/categories", input).then((r) => r.category);
}

export type UpdateCategoryInput = Partial<{
  name: string;
  kind: "fixed" | "variable";
  monthlyLimit: number | null;
  rollover: boolean;
  archived: boolean;
}>;

export function updateCategory(id: number, input: UpdateCategoryInput) {
  return apiClient.patch<{ category: Category }>(`/api/budget/categories/${id}`, input).then((r) => r.category);
}

export function deleteCategory(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean }>(`/api/budget/categories/${id}`);
}

export function payCategory(
  id: number,
  input?: { walletId?: number; amount?: number; occurredAt?: string; createTransaction?: boolean },
) {
  return apiClient.post<{ transaction: Transaction | null; summary: BudgetSnapshot | null }>(
    `/api/budget/categories/${id}/pay`,
    input ?? {},
  );
}

export function unpayCategory(id: number) {
  return apiClient.delete<{ category: Category; summary: BudgetSnapshot | null }>(`/api/budget/categories/${id}/pay`);
}

export function listBills(activeOnly = true) {
  return apiClient.get<{ items: Bill[] }>(`/api/budget/bills?activeOnly=${activeOnly ? 1 : 0}`).then((r) => r.items);
}

export function createBill(input: {
  name: string;
  amount: number;
  dueDay?: number | null;
  categoryId?: number | null;
  walletId?: number | null;
  cadence?: string;
}) {
  return apiClient.post<{ bill: Bill }>("/api/budget/bills", input).then((r) => r.bill);
}

export type UpdateBillInput = Partial<{
  name: string;
  amount: number;
  dueDay: number | null;
  categoryId: number | null;
  walletId: number | null;
  cadence: string;
  active: boolean;
}>;

export function updateBill(id: number, input: UpdateBillInput) {
  return apiClient.patch<{ bill: Bill }>(`/api/budget/bills/${id}`, input).then((r) => r.bill);
}

export function deleteBill(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean }>(`/api/budget/bills/${id}`);
}

export function payBill(id: number, input?: { walletId?: number; amount?: number; occurredAt?: string }) {
  return apiClient.post<{ transaction: Transaction; summary: BudgetSnapshot | null }>(
    `/api/budget/bills/${id}/pay`,
    input ?? {},
  );
}

export function unpayBill(id: number) {
  return apiClient.delete<{ bill: Bill; summary: BudgetSnapshot | null }>(`/api/budget/bills/${id}/pay`);
}

export function getSetupStatus() {
  return apiClient.get<SetupStatus>("/api/budget/setup/status");
}

export function runSetup(input: SetupInput) {
  return apiClient.post<SetupResult>("/api/budget/setup", input);
}

export type TransactionsQuery = {
  categoryId?: number;
  walletId?: number;
  direction?: TransactionDirection;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
};

export async function listTransactions(query: TransactionsQuery = {}): Promise<TransactionsPage> {
  const params = new URLSearchParams();
  if (query.categoryId !== undefined) params.set("categoryId", String(query.categoryId));
  if (query.walletId !== undefined) params.set("walletId", String(query.walletId));
  if (query.direction) params.set("direction", query.direction);
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  params.set("limit", String(query.limit ?? 50));
  params.set("offset", String(query.offset ?? 0));

  const { data, meta } = await apiClient.getFull<
    { items: Transaction[] },
    { total: number; limit: number; offset: number; hasMore: boolean }
  >(`/api/budget/transactions?${params.toString()}`);
  return { items: data.items, ...meta };
}

export type CreateTransactionInput = {
  amount: number;
  direction: TransactionDirection;
  categoryId?: number | null;
  walletId?: number | null;
  note?: string | null;
  occurredAt?: string | null;
};

export function createTransaction(input: CreateTransactionInput) {
  return apiClient.post<{ transaction: Transaction; summary: BudgetSnapshot | null }>(
    "/api/budget/transactions",
    input,
  );
}

export type UpdateTransactionInput = Partial<CreateTransactionInput>;

export function updateTransaction(id: number, input: UpdateTransactionInput) {
  return apiClient.patch<{ transaction: Transaction; summary: BudgetSnapshot | null }>(
    `/api/budget/transactions/${id}`,
    input,
  );
}

export function deleteTransaction(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean; summary: BudgetSnapshot | null }>(
    `/api/budget/transactions/${id}`,
  );
}

export function listGoals(includeArchived = false) {
  const qs = includeArchived ? "?includeArchived=1" : "";
  return apiClient.get<{ items: Goal[] }>(`/api/budget/goals${qs}`).then((r) => r.items);
}

export function createGoal(input: {
  name: string;
  targetAmount: number;
  kind?: GoalKind;
  targetDate?: string | null;
  monthlyContribution?: number | null;
  reserveFromFree?: boolean;
  walletId?: number | null;
}) {
  return apiClient.post<{ goal: Goal }>("/api/budget/goals", input).then((r) => r.goal);
}

export type UpdateGoalInput = Partial<{
  name: string;
  kind: GoalKind;
  targetAmount: number;
  targetDate: string | null;
  monthlyContribution: number | null;
  reserveFromFree: boolean;
  walletId: number | null;
  archived: boolean;
}>;

export function updateGoal(id: number, input: UpdateGoalInput) {
  return apiClient.patch<{ goal: Goal }>(`/api/budget/goals/${id}`, input).then((r) => r.goal);
}

export function deleteGoal(id: number) {
  return apiClient.delete<{ id: number; deleted: boolean }>(`/api/budget/goals/${id}`);
}

export function contributeToGoal(id: number, amount: number, walletId?: number) {
  return apiClient.post<{ goal: Goal; transaction: Transaction | null; summary: BudgetSnapshot | null }>(
    `/api/budget/goals/${id}/contribute`,
    { amount, walletId },
  );
}

export async function listAlerts(unreadOnly = false, limit = 20): Promise<{ items: Alert[]; unreadCount: number }> {
  const params = new URLSearchParams();
  if (unreadOnly) params.set("unreadOnly", "1");
  params.set("limit", String(limit));
  const { data, meta } = await apiClient.getFull<{ items: Alert[] }, { unreadCount: number }>(
    `/api/budget/alerts?${params.toString()}`,
  );
  return { items: data.items, unreadCount: meta.unreadCount };
}

export function markAlertRead(id: number) {
  return apiClient.post<{ id: number; read: boolean }>(`/api/budget/alerts/${id}/read`);
}

export function getAlertPrefs() {
  return apiClient.get<AlertPrefs>("/api/budget/alerts/prefs");
}

export function updateAlertPrefs(input: Partial<AlertPrefs>) {
  return apiClient.patch<AlertPrefs>("/api/budget/alerts/prefs", input);
}

// ================================================================
// WALLET SYNC — manual-trigger two-way sync against Wallet by
// BudgetBakers. See features/budget/wallet/ and docs/BUDGETBAKERS_API.md.
// ================================================================
export function getWalletSyncStatus() {
  return apiClient.get<WalletSyncStatus>("/api/budget/sync/wallet/status");
}

export function previewWalletSync() {
  return apiClient.post<WalletSyncPreview>("/api/budget/sync/wallet/preview");
}

export function pullWalletSync() {
  return apiClient.post<{ pull: WalletPullSummary; summary: BudgetSnapshot | null }>("/api/budget/sync/wallet/pull");
}

export function pushWalletSync() {
  return apiClient.post<{ push: WalletPushSummary }>("/api/budget/sync/wallet/push");
}

export function runWalletSync() {
  return apiClient.post<{ pull: WalletPullSummary; push: WalletPushSummary; summary: BudgetSnapshot | null }>(
    "/api/budget/sync/wallet",
  );
}

export function compareWalletSync() {
  return apiClient.get<WalletSyncCompare>("/api/budget/sync/wallet/compare");
}
