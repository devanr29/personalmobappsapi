import type { TabTriggerSlotProps } from "expo-router/ui";
import type { Icon } from "phosphor-react-native";
import { Pressable } from "react-native";

import { Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { useStyles } from "@/theme/useStyles";

export type TabButtonProps = TabTriggerSlotProps & {
  IconComponent: Icon;
  label: string;
};

export function TabButton({ IconComponent, label, isFocused, ...props }: TabButtonProps) {
  const theme = useTheme();
  const styles = useStyles((t) => ({
    button: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      gap: t.spacing[0.5],
      paddingVertical: t.spacing[1.5],
    },
  }));
  const tint = isFocused ? theme.colors.accent : theme.colors.neutral[500];

  return (
    <Pressable {...props} style={styles.button}>
      <IconComponent size={22} weight={isFocused ? "fill" : "regular"} color={tint} />
      <Text variant="tabLabel" style={{ color: tint }}>
        {label}
      </Text>
    </Pressable>
  );
}
