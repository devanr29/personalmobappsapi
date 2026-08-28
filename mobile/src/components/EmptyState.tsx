import type { Icon } from "phosphor-react-native";

import { Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type EmptyStateProps = {
  message: string;
  IconComponent?: Icon;
};

export function EmptyState({ message, IconComponent }: EmptyStateProps) {
  const theme = useTheme();

  return (
    <Stack align="center" justify="center" p={8} gap={3}>
      {IconComponent ? <IconComponent size={28} color={theme.colors.neutral[600]} /> : null}
      <Text variant="label" tone="muted" align="center">
        {message}
      </Text>
    </Stack>
  );
}
