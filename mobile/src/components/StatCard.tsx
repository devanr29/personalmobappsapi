import type { Icon } from "phosphor-react-native";
import type { ReactNode } from "react";

import { Card } from "./Card";
import { HStack, Stack, Text, type Tone } from "@/theme/primitives";
import type { Theme } from "@/theme/ThemeProvider";
import { useTheme } from "@/theme/ThemeProvider";

export type StatCardProps = {
  IconComponent: Icon;
  value: string;
  valueVariant?: keyof Theme["type"];
  valueTone?: Tone;
  label: string;
  /** Optional chart slot (Meter/Sparkline) — the stat-tile contract's "trend". */
  trend?: ReactNode;
};

export function StatCard({ IconComponent, value, valueVariant = "title", valueTone = "primary", label, trend }: StatCardProps) {
  const theme = useTheme();

  return (
    <Card style={{ flex: 1 }}>
      <Stack gap={2}>
        <HStack align="center" justify="space-between">
          <IconComponent size={20} color={theme.colors.accent} />
          <Text variant={valueVariant} tone={valueTone} numeric>
            {value}
          </Text>
        </HStack>
        <Text variant="meta" tone="muted">
          {label}
        </Text>
        {trend}
      </Stack>
    </Card>
  );
}
