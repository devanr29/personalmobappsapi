import { CheckSquare, Square } from "phosphor-react-native";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, View } from "react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { ApiError } from "@/api/client";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { listTransactions, payBill, payCategory, type PayInput } from "../api";
import type { Transaction } from "../types";
import { formatBudgetDayHeader } from "../utils/budgetDate";

/** The budget item being marked paid. `amount` is what the card shows as
 * its amount (a bill's amount, or a category's limit this period);
 * `spent` is the category's spend already counted this period. */
export type AttachTarget =
  | { kind: "category"; id: number; name: string; amount: number; spent: number }
  | { kind: "bill"; id: number; name: string; amount: number };

export type AttachTransactionSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired after the item is successfully marked paid. */
  onAttached: () => void;
  target: AttachTarget;
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
 * in the sheet rather than via Alert.alert, which is a no-op on web. */
export function AttachTransactionSheet({ visible, onClose, onAttached, target }: AttachTransactionSheetProps) {
  const theme = useTheme();
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
  const sessionKey = visible ? `${target.kind}:${target.id}` : null;
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
        if (!cancelled) setItems(page.items);
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
  }, [visible, target.kind, target.id]);

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
      if (target.kind === "category") {
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
        setError(err instanceof ApiError ? err.message : "Couldn't mark as paid — check your connection and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const declineChange = () => {
    setQuestion(null);
    setNotice(`Not marked as paid — ${target.name} is unchanged.`);
  };

  const subtitle =
    target.kind === "category"
      ? `Pick the expenses that belong to ${target.name} — they're filed under it and the budget is marked paid, without adding new entries.`
      : `Pick the expenses that paid ${target.name} — they settle the bill for this period without logging a duplicate.`;
  const amountLabel = target.kind === "category" ? "limit" : "amount";
  const totalLabel = target.kind === "category" ? "Spent" : "Selected";

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <GlassSurface
          style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg, maxHeight: "82%" }}
        >
          <Stack p={4} gap={3}>
            <Stack gap={1}>
              <Text variant="heading">Attach transactions</Text>
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

            <HStack align="center" justify="space-between" gap={3}>
              <Text variant="caption" tone="muted" numeric style={{ flex: 1 }}>
                {selected.length} selected · {formatRupiah(previewTotal)}
                {target.kind === "category" ? " spent" : ""} vs {formatRupiah(target.amount)}
              </Text>
              <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close">
                <Box py={2} px={3}>
                  <Text variant="label" tone="muted">
                    Close
                  </Text>
                </Box>
              </Pressable>
              {question === null ? (
                <SheetButton
                  label="Attach & mark paid"
                  primary
                  pending={submitting}
                  disabled={selected.length === 0 || submitting}
                  onPress={() => submit()}
                />
              ) : null}
            </HStack>
          </Stack>
        </GlassSurface>
      </View>
    </Modal>
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
