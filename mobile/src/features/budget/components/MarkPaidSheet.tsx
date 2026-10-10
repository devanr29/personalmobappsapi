import { CheckCircle, Paperclip, Receipt, type Icon } from "phosphor-react-native";
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, View } from "react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { ApiError } from "@/api/client";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { payBill, payCategory, type PayInput } from "../api";
import type { AttachTarget } from "./AttachTransactionSheet";

export type MarkPaidSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired after the item is marked paid by one of the first two options. */
  onPaid: () => void;
  /** The third option — the caller closes this sheet and opens
   * AttachTransactionSheet for the same target. */
  onChooseAttach: () => void;
  target: AttachTarget;
};

type Option = "markOnly" | "withTransaction";

/** Asks how a bill or variable category should be marked paid, instead of
 * "Mark as paid" always logging a new expense:
 *
 *  - Just mark as paid: records the "paid" fact only (createTransaction:
 *    false) — the money left some other way, nothing is logged.
 *  - Mark paid & add a transaction: the old one-tap default — logs the
 *    bill amount (or what's left of the category) as a new expense.
 *  - Attach existing transaction(s): settles it with expenses already in
 *    the ledger, via AttachTransactionSheet. */
export function MarkPaidSheet({ visible, onClose, onPaid, onChooseAttach, target }: MarkPaidSheetProps) {
  const theme = useTheme();
  const [pending, setPending] = useState<Option | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sessionKey = visible ? `${target.kind}:${target.id}` : null;
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (sessionKey !== openFor) {
    setOpenFor(sessionKey);
    setPending(null);
    setError(null);
  }

  const pay = async (option: Option) => {
    setPending(option);
    setError(null);
    const input: PayInput = option === "markOnly" ? { createTransaction: false } : {};
    try {
      if (target.kind === "category") {
        await payCategory(target.id, input);
      } else {
        await payBill(target.id, input);
      }
      onPaid();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't mark as paid — check your connection and try again.");
      setPending(null);
    }
  };

  const withTransactionDetail =
    target.kind === "category"
      ? `Logs what's left of the ${formatRupiah(target.amount)} budget as a new expense.`
      : `Logs a ${formatRupiah(target.amount)} expense from the bill's wallet.`;

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
          <Stack p={4} gap={3}>
            <Text variant="heading">Mark {target.name} as paid</Text>

            <OptionRow
              IconComponent={CheckCircle}
              title="Just mark as paid"
              detail="No transaction is added and your balance doesn't change."
              pending={pending === "markOnly"}
              disabled={pending !== null}
              onPress={() => pay("markOnly")}
            />
            <OptionRow
              IconComponent={Receipt}
              title="Mark paid & add a transaction"
              detail={withTransactionDetail}
              pending={pending === "withTransaction"}
              disabled={pending !== null}
              onPress={() => pay("withTransaction")}
            />
            <OptionRow
              IconComponent={Paperclip}
              title="Attach existing transactions…"
              detail="Pick expenses already in your ledger, without logging duplicates."
              disabled={pending !== null}
              onPress={onChooseAttach}
            />

            {error ? (
              <Text variant="label" tone="negative">
                {error}
              </Text>
            ) : null}

            <HStack justify="flex-end">
              <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Cancel">
                <Box py={2} px={4}>
                  <Text variant="label" tone="muted">
                    Cancel
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

function OptionRow({
  IconComponent, title, detail, onPress, pending = false, disabled = false,
}: {
  IconComponent: Icon;
  title: string;
  detail: string;
  onPress: () => void;
  pending?: boolean;
  disabled?: boolean;
}) {
  const theme = useTheme();
  return (
    <PressableScale onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={title}>
      <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
        <HStack align="center" gap={3}>
          {pending ? (
            <ActivityIndicator size="small" color={theme.colors.accent} />
          ) : (
            <IconComponent size={18} color={theme.colors.accent} />
          )}
          <Stack flex={1} gap={0.5}>
            <Text variant="body">{title}</Text>
            <Text variant="caption" tone="faint">
              {detail}
            </Text>
          </Stack>
        </HStack>
      </Box>
    </PressableScale>
  );
}
