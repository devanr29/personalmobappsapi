import { CalendarBlank, CheckCircle, CircleIcon, Paperclip, PencilSimple } from "phosphor-react-native";
import { ActivityIndicator } from "react-native";

import { ExpandableCard } from "@/components/ExpandableCard";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import type { Bill, Wallet } from "../types";
import { SpendInputRow } from "./SpendInputRow";

export type FixedBudgetCardProps = {
  bill: Bill;
  /** Unpaid this period (present in breakdown.stillOwed) vs already paid — a
   * period-scoped fact from budget_bill_payments, not a property of the
   * bill row itself, so it's threaded in rather than read off `bill`. */
  paidThisPeriod: boolean;
  payPending: boolean;
  wallets: Wallet[];
  onEdit: () => void;
  onTogglePaid: () => void;
  onPayAmount: (amount: number, walletId: number) => Promise<void>;
  /** Opens the picker for settling this bill with an expense that's already
   * in the ledger (e.g. pulled from Wallet) instead of logging a fresh
   * payment — see AttachTransactionSheet / service.pay_bill's transaction_id
   * path. */
  onAttachTransaction: () => void;
};

/** One fixed monthly obligation (a bill — rent, subscriptions, etc.) as its
 * own expandable card. Mirrors chat_view.py's "Fixed expenses still to pay"
 * section: an unpaid bill counts toward total_still_owed, which is
 * subtracted from free_money before the daily budget is derived. Marking
 * one paid (via payBill/unpayBill) removes it from that deduction the
 * moment the breakdown is refetched — the wallet balance also drops by the
 * same amount, so free_money itself doesn't move, only which bucket it's
 * sitting in (reserved vs already spent). "Pay a different amount" covers
 * the case where the real payment doesn't match the bill's configured
 * amount (e.g. rent paid at a discount) — service.pay_bill already accepts
 * a custom amount, only unused by the mobile UI until now. */
export function FixedBudgetCard({ bill, paidThisPeriod, payPending, wallets, onEdit, onTogglePaid, onPayAmount, onAttachTransaction }: FixedBudgetCardProps) {
  const theme = useTheme();

  return (
    <ExpandableCard
      accessibilityLabel={`${bill.name}, ${paidThisPeriod ? "paid" : "still owed"} this period`}
      header={() => (
        <HStack align="center" justify="space-between">
          <Stack gap={0.5} style={{ flex: 1 }}>
            <Text variant="label">{bill.name}</Text>
            {bill.dueDay != null ? (
              <HStack align="center" gap={1}>
                <CalendarBlank size={12} color={theme.colors.neutral[500]} />
                <Text variant="caption" tone="faint">
                  Due day {bill.dueDay}
                </Text>
              </HStack>
            ) : null}
          </Stack>
          <Text variant="meta" numeric tone={paidThisPeriod ? "muted" : "primary"}>
            {formatRupiah(bill.amount)}
          </Text>
        </HStack>
      )}
    >
      <Stack gap={3}>
        <PressableScale onPress={onTogglePaid} disabled={payPending} accessibilityRole="button" accessibilityLabel={paidThisPeriod ? "Mark unpaid" : "Mark paid"}>
          <HStack align="center" gap={1.5}>
            {payPending ? (
              <ActivityIndicator size="small" color={theme.colors.accent} />
            ) : paidThisPeriod ? (
              <CheckCircle size={16} color={theme.status.comfortable} weight="fill" />
            ) : (
              <CircleIcon size={16} color={theme.colors.neutral[500]} />
            )}
            <Text variant="caption" tone={paidThisPeriod ? "positive" : "muted"}>
              {paidThisPeriod ? "Paid this period" : "Mark as paid"}
            </Text>
          </HStack>
        </PressableScale>
        {!paidThisPeriod ? (
          <>
            <SpendInputRow
              label="Pay a different amount"
              submitLabel="Pay"
              wallets={wallets}
              onSubmit={(amount, walletId) => onPayAmount(amount, walletId)}
            />
            <PressableScale
              onPress={onAttachTransaction}
              accessibilityRole="button"
              accessibilityLabel={`Attach an existing transaction to ${bill.name}`}
            >
              <HStack align="center" gap={1.5}>
                <Paperclip size={14} color={theme.colors.accent} />
                <Text variant="caption" tone="accent">
                  Attach an existing transaction
                </Text>
              </HStack>
            </PressableScale>
          </>
        ) : null}
        <PressableScale onPress={onEdit} accessibilityRole="button" accessibilityLabel={`Edit ${bill.name}`}>
          <HStack align="center" gap={1.5}>
            <PencilSimple size={14} color={theme.colors.accent} />
            <Text variant="caption" tone="accent">
              Edit
            </Text>
          </HStack>
        </PressableScale>
      </Stack>
    </ExpandableCard>
  );
}
