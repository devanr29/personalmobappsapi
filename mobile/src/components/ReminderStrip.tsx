import { Alarm, CaretRight } from "phosphor-react-native";

import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ReminderStripProps = {
  title: string;
  timeLabel: string;
  onPress?: () => void;
};

export function ReminderStrip({ title, timeLabel, onPress }: ReminderStripProps) {
  const theme = useTheme();

  return (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={`${title}, ${timeLabel}`}>
      <HStack
        align="center"
        gap={3}
        p={4}
        radius="md"
        bg={theme.colors.accentRamp[900]}
        style={{ borderWidth: 1, borderColor: theme.colors.accentRamp[800] }}
      >
        <Alarm size={20} weight="fill" color={theme.colors.accentRamp[300]} />
        <Stack flex={1}>
          <Text variant="label" style={{ color: theme.colors.accentRamp[100] }}>
            {title}
          </Text>
          <Text variant="caption" style={{ color: theme.colors.accentRamp[300] }}>
            {timeLabel}
          </Text>
        </Stack>
        <CaretRight size={15} color={theme.colors.accentRamp[400]} />
      </HStack>
    </PressableScale>
  );
}
