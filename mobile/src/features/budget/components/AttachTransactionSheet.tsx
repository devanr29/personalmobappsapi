import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, View } from "react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { ApiError } from "@/api/client";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { listTransactions, updateTransaction } from "../api";
import type { Transaction } from "../types";
import { formatBudgetDayHeader } from "../utils/budgetDate";

export type AttachTransactionSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired after a transaction is successfully re-filed under this category. */
  onAttached: () => void;
  categoryId: number;
  categoryName: string;
};

const CANDIDATE_LIMIT = 25;

/** Re-files an expense that already exists in the ledger (a Wallet sync, an
 * earlier manual entry) under a variable-budget category, so its amount
 * starts counting toward that category's envelope. It's a plain
 * PATCH /transactions/:id { categoryId } — no new row and no balance change,
 * since the money already moved when the transaction was first recorded.
 *
 * spend_by_category matches on period too, so a transaction only shifts this
 * period's `remaining` if it happened this period — the copy says as much. */
export function AttachTransactionSheet({ visible, onClose, onAttached, categoryId, categoryName }: AttachTransactionSheetProps) {
  const theme = useTheme();
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachingId, setAttachingId] = useState<number | null>(null);

  // Reset + arm a load when the sheet opens (or reopens for another
  // category) — a render-phase adjustment keyed on session identity, the
  // same pattern TransactionSheet uses, so it doesn't cascade the way a
  // synchronous setState in the effect body would.
  const sessionKey = visible ? String(categoryId) : null;
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (sessionKey !== null && openFor !== sessionKey) {
    setOpenFor(sessionKey);
    setItems([]);
    setError(null);
    setAttachingId(null);
    setLoading(true);
  }

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    listTransactions({ direction: "expense", limit: CANDIDATE_LIMIT })
      .then((page) => {
        // Rows already under this category would attach to a no-op.
        if (!cancelled) setItems(page.items.filter((t) => t.categoryId !== categoryId));
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
  }, [visible, categoryId]);

  const handleAttach = async (txn: Transaction) => {
    setAttachingId(txn.id);
    setError(null);
    try {
      await updateTransaction(txn.id, { categoryId });
      onAttached();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't attach — check your connection and try again.");
      setAttachingId(null);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <GlassSurface
          style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg, maxHeight: "82%" }}
        >
          <Stack p={4} gap={3}>
            <Stack gap={1}>
              <Text variant="heading">Attach a transaction</Text>
              <Text variant="caption" tone="muted">
                Pick an expense from this period — it starts counting toward {categoryName} without adding a new entry.
              </Text>
            </Stack>

            {loading ? (
              <Stack py={6} align="center">
                <ActivityIndicator size="small" color={theme.colors.accent} />
              </Stack>
            ) : error ? (
              <Text variant="label" tone="negative">
                {error}
              </Text>
            ) : items.length === 0 ? (
              <Text variant="label" tone="muted">
                No expenses to attach.
              </Text>
            ) : (
              <ScrollView style={{ maxHeight: 380 }} keyboardShouldPersistTaps="handled">
                <Stack gap={2}>
                  {items.map((txn) => (
                    <PressableScale
                      key={txn.id}
                      onPress={() => handleAttach(txn)}
                      disabled={attachingId !== null}
                      accessibilityRole="button"
                      accessibilityLabel={`Attach ${txn.note || txn.categoryName || "transaction"}`}
                    >
                      <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
                        <HStack align="center" gap={3}>
                          <Stack flex={1} gap={0.5}>
                            <Text variant="body">{txn.note || txn.categoryName || "Transaction"}</Text>
                            <Text variant="caption" tone="faint">
                              {[txn.categoryName, txn.walletName, formatBudgetDayHeader(txn.occurredAt)].filter(Boolean).join(" · ")}
                            </Text>
                          </Stack>
                          {attachingId === txn.id ? (
                            <ActivityIndicator size="small" color={theme.colors.accent} />
                          ) : (
                            <Text variant="body" numeric style={{ color: theme.colors.neutral[300] }}>
                              {formatRupiah(txn.amount)}
                            </Text>
                          )}
                        </HStack>
                      </Box>
                    </PressableScale>
                  ))}
                </Stack>
              </ScrollView>
            )}

            <HStack justify="flex-end">
              <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close">
                <Box py={2} px={4}>
                  <Text variant="label" tone="muted">
                    Close
                  </Text>
                </Box>
              </Pressable>
            </HStack>
          </Stack>
        </GlassSurface>
      </View>
    </Modal>
  );
}
