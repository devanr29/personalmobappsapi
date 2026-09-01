import type { Icon } from "phosphor-react-native";
import type { ReactNode } from "react";

import { Card } from "./Card";
import { Box, HStack, Stack, Text, type Tone } from "@/theme/primitives";
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
  /** Which of the 5 design-import tile hues (theme.tile) tints the icon badge. */
  tileIndex?: number;
};

export function StatCard({ IconComponent, value, valueVariant = "title", valueTone = "primary", label, trend, tileIndex }: StatCardProps) {
  const theme = useTheme();
  const tint = tileIndex !== undefined ? theme.tile[tileIndex % theme.tile.length] : null;

  return (
    <Card style={{ flex: 1 }}>
      <Stack gap={2}>
        <HStack align="center" justify="space-between">
          {tint ? (
            <Box radius="md" bg={tint.bg} align="center" justify="center" style={{ width: 36, height: 36 }}>
              <IconComponent size={18} color={tint.fg} />
            </Box>
          ) : (
            <IconComponent size={20} color={theme.colors.accent} />
          )}
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
