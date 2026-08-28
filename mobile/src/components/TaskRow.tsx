import { Check } from "phosphor-react-native";
import { View } from "react-native";

import { Tag } from "./Tag";
import { PressableScale } from "@/theme/motion";
import { HStack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type TaskRowProps = {
  title: string;
  completed: boolean;
  tag?: string;
  onToggle: () => void;
};

const BOX_SIZE = 16;

export function TaskRow({ title, completed, tag, onToggle }: TaskRowProps) {
  const theme = useTheme();

  return (
    <PressableScale
      onPress={onToggle}
      hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: completed }}
      accessibilityLabel={title}
      scaleTo={0.99}
    >
      <HStack align="center" gap={3} style={{ opacity: completed ? 0.5 : 1 }}>
        <View
          style={{
            width: BOX_SIZE,
            height: BOX_SIZE,
            borderRadius: theme.radius.sm,
            borderWidth: completed ? 0 : 1.5,
            borderColor: theme.colors.neutral[600],
            backgroundColor: completed ? theme.colors.accent : "transparent",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {completed ? <Check size={11} weight="bold" color={theme.colors.bg} /> : null}
        </View>
        <Text variant="body" style={{ flex: 1, textDecorationLine: completed ? "line-through" : "none" }}>
          {title}
        </Text>
        {tag ? <Tag label={tag} variant="accent" /> : null}
      </HStack>
    </PressableScale>
  );
}
