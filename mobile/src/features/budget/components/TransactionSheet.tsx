import { useEffect, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, TextInput, View } from "react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { createTransaction, listCategories, listWallets, updateTransaction } from "../api";
import type { Category, Transaction, TransactionDirection, Wallet } from "../types";
import { parseIdr } from "../utils/parseIdr";
import { toNaiveDateTime } from "../utils/budgetDate";
import { ApiError } from "@/api/client";
import { AmountField } from "./AmountField";
import { Chip, ChipRow } from "./Chip";
import type { BudgetSnapshot } from "@/api/types";

export type TransactionSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired with the fresh summary after a successful create/update, so the
   * caller can update in-band instead of a separate GET /api/budget round-trip. */
  onSaved: (summary: BudgetSnapshot | null) => void;
  /** When set, the sheet edits this transaction (PATCH) instead of creating one. */
  editingTransaction?: Transaction | null;
};

type DateChoice = "today" | "yesterday";

const DIRECTIONS: { value: TransactionDirection; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
];

export function TransactionSheet({ visible, onClose, onSaved, editingTransaction }: TransactionSheetProps) {
  const theme = useTheme();
  const isEditing = !!editingTransaction;

  const [amountText, setAmountText] = useState("");
  const [direction, setDirection] = useState<TransactionDirection>("expense");
  const [dateChoice, setDateChoice] = useState<DateChoice>("today");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [walletId, setWalletId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Options load once per time the sheet opens — cheap lists, no point
  // caching across screens for Phase 1.
  useEffect(() => {
    if (!visible) return;
    listCategories().then(setCategories).catch(() => {});
    listWallets().then(setWallets).catch(() => {});
  }, [visible]);

  // Reset the form fields when the sheet opens for a new session (a fresh
  // create, or a different transaction to edit) — a render-phase state
  // adjustment guarded by session identity, not an effect, since setState
  // synchronously inside an effect body triggers a cascading extra render.
  const sessionKey = visible ? (editingTransaction ? `edit-${editingTransaction.id}` : "create") : null;
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (sessionKey !== null && openFor !== sessionKey) {
    setOpenFor(sessionKey);
    setError(null);
    if (editingTransaction) {
      setAmountText(String(editingTransaction.amount));
      setDirection(editingTransaction.direction);
      setDateChoice("today");
      setCategoryId(editingTransaction.categoryId);
      setWalletId(editingTransaction.walletId);
      setNote(editingTransaction.note ?? "");
    } else {
      setAmountText("");
      setDirection("expense");
      setDateChoice("today");
      setCategoryId(null);
      setWalletId(null);
      setNote("");
    }
  }

  const handleClose = () => {
    if (submitting) return;
    onClose();
  };

  const parsedAmount = parseIdr(amountText);
  const canSave = parsedAmount !== null && parsedAmount > 0 && !submitting;

  const handleSave = async () => {
    if (!canSave || parsedAmount === null) return;
    setSubmitting(true);
    setError(null);
    try {
      const occurredAt = (() => {
        if (isEditing || dateChoice === "today") return undefined;
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        return toNaiveDateTime(yesterday);
      })();
      const input = {
        amount: parsedAmount,
        direction,
        categoryId,
        walletId,
        note: note.trim() || null,
        ...(occurredAt ? { occurredAt } : {}),
      };
      const { summary } = isEditing
        ? await updateTransaction(editingTransaction.id, input)
        : await createTransaction(input);
      onSaved(summary);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={handleClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
            <ScrollView>
              <Stack p={4} gap={4}>
                <Text variant="heading">{isEditing ? "Edit transaction" : "Add transaction"}</Text>

                <AmountField rawText={amountText} onChangeRawText={setAmountText} autoFocus />

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    Type
                  </Text>
                  <ChipRow>
                    {DIRECTIONS.map((d) => (
                      <Chip key={d.value} label={d.label} selected={d.value === direction} onPress={() => setDirection(d.value)} />
                    ))}
                  </ChipRow>
                </Stack>

                {!isEditing ? (
                  <Stack gap={1.5}>
                    <Text variant="caption" tone="muted">
                      Date
                    </Text>
                    <ChipRow>
                      <Chip label="Today" selected={dateChoice === "today"} onPress={() => setDateChoice("today")} />
                      <Chip label="Yesterday" selected={dateChoice === "yesterday"} onPress={() => setDateChoice("yesterday")} />
                    </ChipRow>
                  </Stack>
                ) : null}

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    Category
                  </Text>
                  <ChipRow>
                    {categories.map((c) => (
                      <Chip key={c.id} label={c.name} selected={c.id === categoryId} onPress={() => setCategoryId(c.id)} />
                    ))}
                  </ChipRow>
                </Stack>

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    Wallet
                  </Text>
                  <ChipRow>
                    {wallets.map((w) => (
                      <Chip key={w.id} label={w.name} selected={w.id === walletId} onPress={() => setWalletId(w.id)} />
                    ))}
                  </ChipRow>
                </Stack>

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    Note
                  </Text>
                  <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
                    <TextInput
                      value={note}
                      onChangeText={setNote}
                      placeholder="Optional"
                      placeholderTextColor={theme.colors.neutral[500]}
                      style={{ ...theme.type.body, color: theme.colors.text }}
                      editable={!submitting}
                      accessibilityLabel="Note"
                    />
                  </Box>
                </Stack>

                {error ? (
                  <Text variant="label" tone="negative">
                    {error}
                  </Text>
                ) : null}

                <HStack justify="flex-end" gap={3}>
                  <Pressable onPress={handleClose} disabled={submitting} accessibilityRole="button" accessibilityLabel="Cancel">
                    <Box py={2} px={4}>
                      <Text variant="label" tone="muted">
                        Cancel
                      </Text>
                    </Box>
                  </Pressable>
                  <Pressable onPress={handleSave} disabled={!canSave} accessibilityRole="button" accessibilityLabel="Save">
                    <HStack
                      align="center"
                      gap={1.5}
                      py={2}
                      px={4}
                      radius="pill"
                      bg={theme.colors.accent}
                      style={{ opacity: canSave ? 1 : 0.5 }}
                    >
                      {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
                      <Text variant="label" style={{ color: theme.colors.bg }}>
                        Save
                      </Text>
                    </HStack>
                  </Pressable>
                </HStack>
              </Stack>
            </ScrollView>
          </GlassSurface>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}
