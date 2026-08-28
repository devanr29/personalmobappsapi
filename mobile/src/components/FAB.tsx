import type { Icon } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { useTheme } from "@/theme/ThemeProvider";

export type FABProps = {
  IconComponent: Icon;
  onPress: () => void;
  accessibilityLabel: string;
};

const SIZE = 42;

export function FAB({ IconComponent, onPress, accessibilityLabel }: FABProps) {
  const theme = useTheme();

  return (
    <PressableScale
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={{
        position: "absolute",
        right: theme.spacing[4],
        bottom: theme.spacing[4],
        width: SIZE,
        height: SIZE,
        borderRadius: theme.radius.full,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: theme.colors.accent,
        ...theme.elevation.md,
      }}
    >
      <IconComponent size={20} weight="fill" color={theme.colors.bg} />
    </PressableScale>
  );
}
