import type { Icon } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { Box, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ShortcutTileProps = {
  IconComponent: Icon;
  label: string;
  onPress?: () => void;
  /** Which of the 5 design-import tile hues (theme.tile) tints this icon —
   * omit for the plain surface/accent treatment used outside Quick Access. */
  tileIndex?: number;
};

export function ShortcutTile({ IconComponent, label, onPress, tileIndex }: ShortcutTileProps) {
  const theme = useTheme();
  const tint = tileIndex !== undefined ? theme.tile[tileIndex % theme.tile.length] : null;

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
          bg={tint ? tint.bg : theme.colors.surface}
          elevationLevel={tint ? undefined : "sm"}
          align="center"
          justify="center"
          style={{ width: "100%", aspectRatio: 1 }}
        >
          <IconComponent size={22} color={tint ? tint.fg : theme.colors.accent} />
        </Box>
        <Text variant="caption" tone="muted">
          {label}
        </Text>
      </Stack>
    </PressableScale>
  );
}
