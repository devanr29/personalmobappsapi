import { CheckSquare, Square } from "phosphor-react-native";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView } from "react-native";

import { ApiError } from "@/api/client";
import { BottomSheet } from "@/components/BottomSheet";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { attachCategorySpend, listTransactions, payBill, payCategory, type PayInput } from "../api";
import type { Transaction } from "../types";
import { formatBudgetDayHeader } from "../utils/budgetDate";

/** The budget item being marked paid. `amount` is what the card shows as
 * its amount (a bill's amount, or a category's limit this period);
 * `spent` is the category's spend already counted this period. */
export type AttachTarget =
  | { kind: "category"; id: number; name: string; amount: number; spent: number }
  | { kind: "bill"; id: number; name: string; amount: number };

/** "pay" settles the item with the picked expenses (marks it paid, with the
 * amount check); "spend" — categories only — just files them under it as
 * this period's spend, so its remaining drops and it stays unpaid. */
export type AttachMode = "pay" | "spend";

export type AttachTransactionSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired after the expenses are successfully attached. */
  onAttached: () => void;
  target: AttachTarget;
  mode?: AttachMode;
};

const CANDIDATE_LIMIT = 25;

/** Asked when the selected total differs from the card amount: first
 * whether to change the amount at all, then for how long. */
type AmountQuestion = { step: "change" | "scope"; total: number; amount: number } | null;

/** Marks a bill or variable category paid with expenses that already exist
 * in the ledger (a Wallet sync, earlier manual entries) — no new rows and
 * no balance change, since the money already moved when they were first
 * recorded. Pick one or more; they're re-filed under the item and linked
 * to its payment (POST /bills|categories/:id/pay { transactionIds }).
 *
 * The server compares the total with the card amount — for a category,
 * the period spend once these are filed under it — and answers 409
 * AMOUNT_MISMATCH when they differ. The sheet then asks "Change the
 * amount?": No leaves the item unpaid, Yes asks "this period only" vs
 * "permanently" and resubmits with amountChange. The questions are shown
 * in the sheet rather than via Alert.alert, which is a no-op on web.
 *
 * In "spend" mode (a variable card's "Log spend" section) the picked
 * expenses are only re-filed under the category (POST
 * /categories/:id/spend): no payment, no question — e.g. a 40.000 limit
 * with a 20.000 expense attached reads 20.000 left. */
export function AttachTransactionSheet({ visible, onClose, onAttached, target, mode = "pay" }: AttachTransactionSheetProps) {
  const theme = useTheme();
  const spendMode = mode === "spend" && target.kind === "category";
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [question, setQuestion] = useState<AmountQuestion>(null);

  // Reset + arm a load when the sheet opens (or reopens for another
  // target) — a render-phase adjustment keyed on session identity, the
  // same pattern TransactionSheet uses, so it doesn't cascade the way a
  // synchronous setState in the effect body would.
  const sessionKey = visible ? `${mode}:${target.kind}:${target.id}` : null;
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (sessionKey !== null && openFor !== sessionKey) {
    setOpenFor(sessionKey);
    setItems([]);
    setError(null);
    setNotice(null);
    setSelectedIds(new Set());
    setSubmitting(false);
    setQuestion(null);
    setLoading(true);
  }
  if (sessionKey === null && openFor !== null) {
    setOpenFor(null);
  }

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    listTransactions({ direction: "expense", limit: CANDIDATE_LIMIT })
      .then((page) => {
        // Expenses already filed under the category add nothing as spend.
        if (!cancelled) setItems(spendMode ? page.items.filter((t) => t.categoryId !== target.id) : page.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Couldn't load transactions.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, target.kind, target.id, spendMode]);

  const toggle = (id: number) => {
    setNotice(null);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selected = items.filter((t) => selectedIds.has(t.id));
  const selectedTotal = selected.reduce((sum, t) => sum + t.amount, 0);
  // Client-side preview of what the server compares; the server's number
  // (from AMOUNT_MISMATCH details) is the one the question shows.
  const previewTotal =
    target.kind === "category"
      ? target.spent + selected.filter((t) => t.categoryId !== target.id).reduce((sum, t) => sum + t.amount, 0)
      : selectedTotal;

  const submit = async (amountChange?: PayInput["amountChange"]) => {
    if (selected.length === 0) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const input: PayInput = { transactionIds: selected.map((t) => t.id), amountChange };
    try {
      if (spendMode) {
        await attachCategorySpend(target.id, input.transactionIds ?? []);
      } else if (target.kind === "category") {
        await payCategory(target.id, input);
      } else {
        await payBill(target.id, input);
      }
      setQuestion(null);
      onAttached();
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "AMOUNT_MISMATCH" && amountChange === undefined) {
        const details = err.details ?? {};
        setQuestion({
          step: "change",
          total: Number(details.total ?? previewTotal),
          amount: Number(details.amount ?? target.amount),
        });
      } else {
        setQuestion(null);
        const fallback = spendMode ? "Couldn't add to spend" : "Couldn't mark as paid";
        setError(err instanceof ApiError ? err.message : `${fallback} — check your connection and try again.`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const declineChange = () => {
    setQuestion(null);
    setNotice(`Not marked as paid — ${target.name} is unchanged.`);
  };

  const subtitle = spendMode
    ? `Pick expenses you've already recorded that belong to ${target.name} — they're filed under it and count toward this period's spend, without marking it paid.`
    : target.kind === "category"
      ? `Pick the expenses that belong to ${target.name} — they're filed under it and the budget is marked paid, without adding new entries.`
      : `Pick the expenses that paid ${target.name} — they settle the bill for this period without logging a duplicate.`;
  const amountLabel = target.kind === "category" ? "limit" : "amount";
  const totalLabel = target.kind === "category" ? "Spent" : "Selected";

  return (
    <BottomSheet visible={visible} onClose={onClose} dismissDisabled={submitting} maxHeight="82%">
      <Stack p={4} gap={3}>
        <Stack gap={1}>
          <Text variant="heading">{spendMode ? "Add to spend" : "Attach transactions"}</Text>
          <Text variant="caption" tone="muted">
            {subtitle}
          </Text>
        </Stack>

        {loading ? (
          <Stack py={6} align="center">
            <ActivityIndicator size="small" color={theme.colors.accent} />
          </Stack>
        ) : items.length === 0 && !error ? (
          <Text variant="label" tone="muted">
            No expenses to attach.
          </Text>
        ) : (
          <ScrollView style={{ maxHeight: 340 }} keyboardShouldPersistTaps="handled">
            <Stack gap={2}>
              {items.map((txn) => {
                const checked = selectedIds.has(txn.id);
                const label = txn.note || txn.categoryName || "Transaction";
                return (
                  <PressableScale
                    key={txn.id}
                    onPress={() => toggle(txn.id)}
                    disabled={submitting || question !== null}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked }}
                    accessibilityLabel={`${label}, ${formatRupiah(txn.amount)}`}
                  >
                    <Box
                      p={3}
                      radius="md"
                      bg={theme.colors.bg}
                      style={{ borderWidth: 1, borderColor: checked ? theme.colors.accent : theme.colors.divider }}
                    >
                      <HStack align="center" gap={3}>
                        {checked ? (
                          <CheckSquare size={18} color={theme.colors.accent} weight="fill" />
                        ) : (
                          <Square size={18} color={theme.colors.neutral[500]} />
                        )}
                        <Stack flex={1} gap={0.5}>
                          <Text variant="body">{label}</Text>
                          <Text variant="caption" tone="faint">
                            {[txn.categoryName, txn.walletName, formatBudgetDayHeader(txn.occurredAt)].filter(Boolean).join(" · ")}
                          </Text>
                        </Stack>
                        <Text variant="body" numeric style={{ color: theme.colors.neutral[300] }}>
                          {formatRupiah(txn.amount)}
                        </Text>
                      </HStack>
                    </Box>
                  </PressableScale>
                );
              })}
            </Stack>
          </ScrollView>
        )}

        {error ? (
          <Text variant="label" tone="negative">
            {error}
          </Text>
        ) : null}
        {notice ? (
          <Text variant="label" tone="muted">
            {notice}
          </Text>
        ) : null}

        {question ? (
          <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
            {question.step === "change" ? (
              <Stack gap={2}>
                <Text variant="label">Amount differs</Text>
                <Text variant="caption" tone="muted">
                  {totalLabel} {formatRupiah(question.total)} ≠ {target.name}&rsquo;s {amountLabel}{" "}
                  {formatRupiah(question.amount)}. Change the {amountLabel}?
                </Text>
                <HStack justify="flex-end" gap={2}>
                  <SheetButton label="No" onPress={declineChange} />
                  <SheetButton
                    label="Yes"
                    primary
                    onPress={() => setQuestion({ ...question, step: "scope" })}
                  />
                </HStack>
              </Stack>
            ) : (
              <Stack gap={2}>
                <Text variant="label">Apply {formatRupiah(question.total)} to:</Text>
                <HStack justify="flex-end" gap={2} wrap>
                  <SheetButton label="Cancel" onPress={declineChange} disabled={submitting} />
                  <SheetButton label="This period only" onPress={() => submit("period")} disabled={submitting} />
                  <SheetButton label="Permanently" primary onPress={() => submit("permanent")} disabled={submitting} />
                </HStack>
              </Stack>
            )}
          </Box>
        ) : null}

        {/* The running total gets its own line: sharing a row with both
         * buttons left it ~120pt wide on a phone, wrapping to 3-4 lines. */}
        <Text variant="caption" tone="muted" numeric>
          {spendMode
            ? `${selected.length} selected · ${formatRupiah(previewTotal)} of ${formatRupiah(target.amount)} · ${
                previewTotal > target.amount
                  ? `over by ${formatRupiah(previewTotal - target.amount)}`
                  : `${formatRupiah(target.amount - previewTotal)} left`
              }`
            : `${selected.length} selected · ${formatRupiah(previewTotal)}${target.kind === "category" ? " spent" : ""} vs ${formatRupiah(target.amount)}`}
        </Text>
        <HStack align="center" justify="flex-end" gap={2}>
          <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close">
            <Box py={2} px={3}>
              <Text variant="label" tone="muted">
                Close
              </Text>
            </Box>
          </Pressable>
          {question === null ? (
            <SheetButton
              label={spendMode ? "Add to spend" : "Attach & mark paid"}
              primary
              pending={submitting}
              disabled={selected.length === 0 || submitting}
              onPress={() => submit()}
            />
          ) : null}
        </HStack>
      </Stack>
    </BottomSheet>
  );
}

function SheetButton({
  label, onPress, primary = false, disabled = false, pending = false,
}: { label: string; onPress: () => void; primary?: boolean; disabled?: boolean; pending?: boolean }) {
  const theme = useTheme();
  return (
    <PressableScale onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={label}>
      <Box
        py={2}
        px={3}
        radius="md"
        bg={primary ? theme.colors.accent : "transparent"}
        style={{
          borderWidth: primary ? 0 : 1,
          borderColor: theme.colors.divider,
          opacity: disabled && !pending ? 0.5 : 1,
        }}
      >
        {pending ? (
          <ActivityIndicator size="small" color={primary ? theme.colors.bg : theme.colors.accent} />
        ) : (
          <Text variant="label" style={{ color: primary ? theme.colors.bg : theme.colors.text }}>
            {label}
          </Text>
        )}
      </Box>
    </PressableScale>
  );
}
