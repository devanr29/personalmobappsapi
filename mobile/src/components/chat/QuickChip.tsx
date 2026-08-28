import { PressableScale } from "@/theme/motion";
import { Box, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type QuickChipProps = {
  label: string;
  onPress: () => void;
};

export function QuickChip({ label, onPress }: QuickChipProps) {
  const theme = useTheme();

  return (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
      <Box py={1.5} px={3} radius="md" style={{ borderWidth: 1, borderColor: theme.colors.neutral[700] }}>
        <Text variant="meta" tone="secondary" style={{ fontFamily: theme.fontFamily.medium }}>
          {label}
        </Text>
      </Box>
    </PressableScale>
  );
}
