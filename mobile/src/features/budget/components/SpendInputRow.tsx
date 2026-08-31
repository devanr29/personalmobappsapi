import { useState } from "react";
import { ActivityIndicator, Pressable, Switch } from "react-native";
import { ArrowRight } from "phosphor-react-native";

import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { ApiError } from "@/api/client";
import { parseIdr } from "../utils/parseIdr";
import type { Wallet } from "../types";
import { AmountField } from "./AmountField";
import { Chip, ChipRow } from "./Chip";

export type SpendInputRowProps = {
  label: string;
  submitLabel: string;
  /** Full wallet list from the breakdown — filtered here to spendable,
   * non-archived options so every caller doesn't repeat that filter. */
  wallets: Wallet[];
  /** Shows a "Record as transaction" switch, default on. Only meaningful to
   * callers that branch on the third onSubmit argument — VariableCategoryCard's
   * "mark as paid" flow, where declaring a budget settled and logging a real
   * expense for it are two separate choices. Bills always create a
   * transaction, so FixedBudgetCard leaves this off. */
  showTransactionToggle?: boolean;
  /** Shows an "Already spent from wallet" switch, default off. When on, the
   * wallet picker hides and onSubmit's walletId is null — the caller records
   * the spend against the budget envelope for money that already left the
   * wallet via an existing transaction, so it isn't deducted twice. Mutually
   * exclusive with showTransactionToggle. */
  logOnlyToggle?: boolean;
  onSubmit: (amount: number, walletId: number | null, flag: boolean) => Promise<void>;
};

/** Inline "log an amount against this budget row" control — a compact
 * amount field, a wallet picker, and a submit button, all in one card
 * section. Used by VariableCategoryCard (logs an expense, or marks paid
 * with a custom amount) and FixedBudgetCard (pays a bill for less than its
 * full amount). A wallet is mandatory: posting an expense without one
 * leaves money_in_hand() unchanged while still reducing the budget's
 * remaining amount, which would push freeMoney up instead of down. */
export function SpendInputRow({ label, submitLabel, wallets, showTransactionToggle = false, logOnlyToggle = false, onSubmit }: SpendInputRowProps) {
  const theme = useTheme();
  const options = wallets.filter((w) => w.spendable && !w.archived);
  const defaultWalletId = options.find((w) => w.isDefault)?.id ?? options[0]?.id ?? null;

  const [rawText, setRawText] = useState("");
  const [walletId, setWalletId] = useState<number | null>(defaultWalletId);
  const [createTransaction, setCreateTransaction] = useState(true);
  const [logOnly, setLogOnly] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedAmount = parseIdr(rawText);
  const needsWallet = !(logOnlyToggle && logOnly);
  const canSubmit = parsedAmount !== null && parsedAmount > 0 && (!needsWallet || walletId !== null) && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit || parsedAmount === null || (needsWallet && walletId === null)) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(parsedAmount, needsWallet ? walletId : null, logOnlyToggle ? logOnly : createTransaction);
      setRawText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (options.length === 0) return null;

  return (
    <Stack gap={2}>
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      <HStack align="center" gap={2}>
        <Box flex={1}>
          <AmountField rawText={rawText} onChangeRawText={setRawText} compact />
        </Box>
        <Pressable
          onPress={handleSubmit}
          disabled={!canSubmit}
          accessibilityRole="button"
          accessibilityLabel={submitLabel}
        >
          <Box p={3} radius="pill" bg={theme.colors.accent} style={{ opacity: canSubmit ? 1 : 0.5 }}>
            {submitting ? (
              <ActivityIndicator size="small" color={theme.colors.bg} />
            ) : (
              <ArrowRight size={16} color={theme.colors.bg} weight="bold" />
            )}
          </Box>
        </Pressable>
      </HStack>
      {needsWallet ? (
        <ChipRow>
          {options.map((w) => (
            <Chip key={w.id} label={w.name} selected={w.id === walletId} onPress={() => setWalletId(w.id)} />
          ))}
        </ChipRow>
      ) : null}
      {showTransactionToggle ? (
        <HStack align="center" justify="space-between">
          <Text variant="caption" tone="muted">
            Record as transaction
          </Text>
          <Switch
            value={createTransaction}
            onValueChange={setCreateTransaction}
            trackColor={{ false: theme.colors.neutral[700], true: theme.colors.accent }}
          />
        </HStack>
      ) : null}
      {logOnlyToggle ? (
        <Stack gap={0.5}>
          <HStack align="center" justify="space-between">
            <Text variant="caption" tone="muted">
              Already spent from wallet
            </Text>
            <Switch
              value={logOnly}
              onValueChange={setLogOnly}
              trackColor={{ false: theme.colors.neutral[700], true: theme.colors.accent }}
            />
          </HStack>
          {logOnly ? (
            <Text variant="caption" tone="faint">
              Only updates this budget — the wallet balance already reflects it.
            </Text>
          ) : null}
        </Stack>
      ) : null}
      {error ? (
        <Text variant="label" tone="negative">
          {error}
        </Text>
      ) : null}
    </Stack>
  );
}
