import type { Icon } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { Box, HStack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type QuickChipProps = {
  label: string;
  IconComponent?: Icon;
  onPress: () => void;
};

export function QuickChip({ label, IconComponent, onPress }: QuickChipProps) {
  const theme = useTheme();

  return (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
      <Box py={1.5} px={3} radius="md" style={{ borderWidth: 1, borderColor: theme.colors.neutral[700] }}>
        <HStack align="center" gap={1.5}>
          {IconComponent ? <IconComponent size={13} color={theme.colors.neutral[300]} /> : null}
          <Text variant="meta" tone="secondary" style={{ fontFamily: theme.fontFamily.medium }}>
            {label}
          </Text>
        </HStack>
      </Box>
    </PressableScale>
  );
}
