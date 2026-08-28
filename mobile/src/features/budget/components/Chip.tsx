import type { ReactNode } from "react";
import { Pressable, ScrollView } from "react-native";

import { Box, HStack, Text, type Tone } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

/** Horizontal scroller for a row of Chips — used anywhere a picker needs to
 * fit an unbounded list of options (wallets, categories) in one row. */
export function ChipRow({ children }: { children: ReactNode }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <HStack gap={2}>{children}</HStack>
    </ScrollView>
  );
}

export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const theme = useTheme();
  const tone: Tone = selected ? "accent" : "secondary";

  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
      <Box
        py={1.5}
        px={3}
        radius="pill"
        bg={selected ? theme.colors.accentRamp[900] : theme.colors.neutral[800]}
        style={{ borderWidth: 1, borderColor: selected ? theme.colors.accentRamp[700] : "transparent" }}
      >
        <Text variant="label" tone={tone}>
          {label}
        </Text>
      </Box>
    </Pressable>
  );
}
