import { Wallet } from "phosphor-react-native";

import { AnimatedCurrency } from "./AnimatedCurrency";
import { Card } from "./Card";
import { Meter, clamp01 } from "@/components/charts";
import type { BudgetSnapshot } from "@/api/types";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";

export type BudgetCardProps = {
  data: BudgetSnapshot | null;
  onSetup?: () => void;
};

export function BudgetCard({ data, onSetup }: BudgetCardProps) {
  const theme = useTheme();

  if (!data) {
    return (
      <Card>
        <Stack gap={3}>
          <HStack align="center" gap={3}>
            <Box radius="md" bg={theme.tile[2].bg} align="center" justify="center" style={{ width: 32, height: 32 }}>
            <Wallet size={16} color={theme.tile[2].fg} />
          </Box>
            <Text variant="label" tone="secondary" style={{ flex: 1 }}>
              Daily budget
            </Text>
          </HStack>
          <Text variant="label" tone="muted">
            No budget set up yet. Open the Budget tab to add your wallets and categories.
          </Text>
          <PressableScale onPress={onSetup} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text variant="meta" tone="accent" style={{ fontFamily: theme.fontFamily.medium }}>
              Set up budget →
            </Text>
          </PressableScale>
        </Stack>
      </Card>
    );
  }

  // Overspend must clamp to 0, never render as a negative-width bar.
  const progress = data.remaining > 0 ? clamp01(data.free / data.remaining) : 0;
  const status = theme.status[data.statusLevel];

  return (
    <Card>
      <Stack gap={3}>
        <HStack align="center" gap={3}>
          <Box radius="md" bg={theme.tile[2].bg} align="center" justify="center" style={{ width: 32, height: 32 }}>
            <Wallet size={16} color={theme.tile[2].fg} />
          </Box>
          <Text variant="label" tone="secondary" style={{ flex: 1 }}>
            Daily budget
          </Text>
          <Text variant="caption" tone="muted">
            {data.daysToPayday} days to payday
          </Text>
        </HStack>
        <HStack align="baseline" gap={1.5}>
          <AnimatedCurrency value={data.dailyBudget} variant="bigNumber" />
          <Text variant="label" tone="muted">
            /day
          </Text>
        </HStack>
        <Meter value={progress} color={status} />
        <HStack justify="space-between">
          <Text variant="caption" tone="muted" numeric>
            Left {formatRupiah(data.free)}
          </Text>
          <Text variant="caption" tone="muted" numeric>
            of {formatRupiah(data.remaining)}
          </Text>
        </HStack>
      </Stack>
    </Card>
  );
}
