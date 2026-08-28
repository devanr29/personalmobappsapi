import { CheckCircle, CircleIcon, PencilSimple } from "phosphor-react-native";
import { ActivityIndicator } from "react-native";

import { ExpandableCard } from "@/components/ExpandableCard";
import { Meter, clamp01 } from "@/components/charts";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import type { BudgetVariableItem, Category, Wallet } from "../types";
import { SpendInputRow } from "./SpendInputRow";

export type VariableCategoryCardProps = {
  item: BudgetVariableItem;
  category: Category | undefined;
  wallets: Wallet[];
  payPending: boolean;
  onEdit: () => void;
  onLogSpend: (amount: number, walletId: number) => Promise<void>;
  onTogglePaid: () => void;
  onPayAmount: (amount: number, walletId: number, createTransaction: boolean) => Promise<void>;
};

/** One variable-budget category (kind='variable') as its own expandable
 * card. `item` carries this period's computed spend/remaining (from
 * GET /breakdown); `category` carries the editable row (id + monthlyLimit)
 * from GET /categories — matched by categoryId in budget/index.tsx. Editing
 * the limit here PATCHes budget_categories directly, which the next
 * breakdown fetch folds straight into total_var_remaining -> free_money ->
 * dailyBudget, so there's no separate "apply" step. Logging spend via
 * SpendInputRow posts a real expense transaction against this category,
 * which reduces `remaining` the same way any other spend does.
 *
 * "Mark as paid" is a separate declaration from logging spend — it mirrors
 * FixedBudgetCard's bill toggle (see service.pay_variable_category):
 * remaining reads as 0 for the rest of the period the moment it's set,
 * whether or not the amount was ever logged as a real transaction. The
 * "Pay a different amount" row's "Record as transaction" switch is where
 * that choice is made explicit for a custom amount; the one-tap toggle
 * button always records one (server default). */
export function VariableCategoryCard({ item, category, wallets, payPending, onEdit, onLogSpend, onTogglePaid, onPayAmount }: VariableCategoryCardProps) {
  const theme = useTheme();
  const limit = category?.monthlyLimit ?? item.remaining + item.spent - item.overBudget;
  const progress = limit > 0 ? clamp01(item.spent / limit) : 0;
  const isOver = item.overBudget > 0;
  const color = isOver ? theme.status.short : theme.colors.accent;

  return (
    <ExpandableCard
      accessibilityLabel={`${item.name}, ${isOver ? "over budget" : "expand for details"}`}
      header={() => (
        <Stack gap={1.5} style={{ flex: 1 }}>
          <HStack justify="space-between">
            <Text variant="label">{item.name}</Text>
            <Text variant="meta" numeric style={{ color: isOver ? theme.status.short : theme.colors.neutral[400] }}>
              {isOver ? `Over by ${formatRupiah(item.overBudget)}` : `${formatRupiah(item.remaining)} left`}
            </Text>
          </HStack>
          <Meter value={progress} color={color} />
        </Stack>
      )}
    >
      <Stack gap={3}>
        <HStack justify="space-between">
          <Text variant="caption" tone="muted">
            Spent
          </Text>
          <Text variant="caption" tone="muted" numeric>
            {formatRupiah(item.spent)} of {formatRupiah(limit)}
          </Text>
        </HStack>
        {item.categoryId != null ? (
          <>
            <PressableScale onPress={onTogglePaid} disabled={payPending} accessibilityRole="button" accessibilityLabel={item.paid ? "Mark unpaid" : "Mark paid"}>
              <HStack align="center" gap={1.5}>
                {payPending ? (
                  <ActivityIndicator size="small" color={theme.colors.accent} />
                ) : item.paid ? (
                  <CheckCircle size={16} color={theme.status.comfortable} weight="fill" />
                ) : (
                  <CircleIcon size={16} color={theme.colors.neutral[500]} />
                )}
                <Text variant="caption" tone={item.paid ? "positive" : "muted"}>
                  {item.paid ? "Paid this period" : "Mark as paid"}
                </Text>
              </HStack>
            </PressableScale>
            {!item.paid ? (
              <SpendInputRow
                label="Pay a different amount"
                submitLabel="Pay"
                wallets={wallets}
                showTransactionToggle
                onSubmit={(amount, walletId, createTransaction) => onPayAmount(amount, walletId, createTransaction)}
              />
            ) : null}
            <SpendInputRow
              label="Log spend"
              submitLabel="Log"
              wallets={wallets}
              onSubmit={(amount, walletId) => onLogSpend(amount, walletId)}
            />
          </>
        ) : null}
        <PressableScale onPress={onEdit} accessibilityRole="button" accessibilityLabel={`Edit ${item.name}`}>
          <HStack align="center" gap={1.5}>
            <PencilSimple size={14} color={theme.colors.accent} />
            <Text variant="caption" tone="accent">
              Edit limit
            </Text>
          </HStack>
        </PressableScale>
      </Stack>
    </ExpandableCard>
  );
}
