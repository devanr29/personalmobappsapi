import { Microphone, Sparkle } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { HStack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type AskBarProps = {
  onPress: () => void;
};

export function AskBar({ onPress }: AskBarProps) {
  const theme = useTheme();

  return (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel="Ask your assistant anything">
      <HStack
        align="center"
        gap={3}
        py={3}
        px={4}
        radius="lg"
        bg={theme.colors.surface}
        elevationLevel="sm"
      >
        <Sparkle size={18} weight="fill" color={theme.colors.accent} />
        <Text variant="body" tone="muted" style={{ flex: 1 }}>
          Ask your assistant anything…
        </Text>
        <Microphone size={18} color={theme.colors.neutral[400]} />
      </HStack>
    </PressableScale>
  );
}
