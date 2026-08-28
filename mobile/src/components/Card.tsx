import type { ReactNode } from "react";
import type { StyleProp, ViewStyle } from "react-native";

import { Box } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import type { SpacingKey } from "@/theme/tokens";

export type CardProps = {
  children: ReactNode;
  padding?: SpacingKey;
  style?: StyleProp<ViewStyle>;
};

export function Card({ children, padding = 4, style }: CardProps) {
  const theme = useTheme();

  return (
    <Box p={padding} radius="md" bg={theme.colors.surface} elevationLevel="sm" style={style}>
      {children}
    </Box>
  );
}
