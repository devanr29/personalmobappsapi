import type { Icon } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { Box, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ShortcutTileProps = {
  IconComponent: Icon;
  label: string;
  onPress?: () => void;
};

export function ShortcutTile({ IconComponent, label, onPress }: ShortcutTileProps) {
  const theme = useTheme();

  return (
    <PressableScale
      onPress={onPress}
      style={{ flex: 1, alignItems: "center" }}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Stack gap={2} align="center" style={{ width: "100%" }}>
        <Box
          radius="md"
          bg={theme.colors.surface}
          elevationLevel="sm"
          align="center"
          justify="center"
          style={{ width: "100%", aspectRatio: 1 }}
        >
          <IconComponent size={22} color={theme.colors.accent} />
        </Box>
        <Text variant="caption" tone="muted">
          {label}
        </Text>
      </Stack>
    </PressableScale>
  );
}
