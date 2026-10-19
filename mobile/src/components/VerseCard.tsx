import { BookOpenText } from "phosphor-react-native";

import { Card } from "./Card";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type VerseCardProps = {
  refLabel: string;
  surah: string;
  translation: string;
  onPress: () => void;
};

export function VerseCard({ refLabel, surah, translation, onPress }: VerseCardProps) {
  const theme = useTheme();

  return (
    <PressableScale
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Verse of the day, ${surah} ${refLabel}: ${translation}. Open reflection in chat`}
    >
      <Card>
        <Stack gap={1.5}>
          <BookOpenText size={17} weight="fill" color={theme.colors.accent} />
          <Text variant="body" tone="secondary">
            {translation}
          </Text>
          <HStack justify="space-between" align="center">
            <Text variant="meta" tone="muted">
              QS {surah} {refLabel}
            </Text>
            <Text variant="meta" tone="accent">
              Tap to reflect
            </Text>
          </HStack>
        </Stack>
      </Card>
    </PressableScale>
  );
}
