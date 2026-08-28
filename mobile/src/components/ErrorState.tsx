import { PressableScale } from "@/theme/motion";
import { Box, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ErrorStateProps = {
  message: string;
  onRetry: () => void;
};

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  const theme = useTheme();

  return (
    <Stack flex={1} bg={theme.colors.bg} align="center" justify="center" p={6} gap={3}>
      <Text variant="cardTitle" align="center">
        {message}
      </Text>
      <PressableScale onPress={onRetry} accessibilityRole="button" accessibilityLabel="Retry loading">
        <Box py={2} px={4} radius="pill" bg={theme.colors.surface}>
          <Text variant="label" tone="accent">
            Try again
          </Text>
        </Box>
      </PressableScale>
    </Stack>
  );
}
