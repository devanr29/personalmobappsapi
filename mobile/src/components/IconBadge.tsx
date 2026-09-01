import type { Icon } from "phosphor-react-native";

import { Box } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type IconBadgeTone = "accent" | "positive" | "negative" | "tight" | "neutral";

export type IconBadgeProps = {
  IconComponent: Icon;
  tone?: IconBadgeTone;
  size?: number;
};

const DEFAULT_SIZE = 36;

export function IconBadge({ IconComponent, tone = "neutral", size = DEFAULT_SIZE }: IconBadgeProps) {
  const theme = useTheme();

  const fg =
    tone === "accent"
      ? theme.colors.accent
      : tone === "positive"
        ? theme.status.comfortable
        : tone === "negative"
          ? theme.status.short
          : tone === "tight"
            ? theme.status.tight
            : theme.colors.neutral[300];
  // Neutral stays a flat surface tint; every other tone gets a translucent
  // wash of its own foreground color so the badge and icon read as one hue.
  const bg = tone === "neutral" ? theme.colors.neutral[800] : `${fg}26`;

  return (
    <Box radius="full" bg={bg} align="center" justify="center" style={{ width: size, height: size }}>
      <IconComponent size={Math.round(size * 0.5)} weight="bold" color={fg} />
    </Box>
  );
}
