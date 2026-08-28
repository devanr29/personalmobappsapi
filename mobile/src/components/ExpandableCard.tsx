import { useState, type ReactNode } from "react";
import Animated from "react-native-reanimated";
import { CaretDown } from "phosphor-react-native";

import { Card } from "@/components/Card";
import { useEntrance, PressableScale } from "@/theme/motion";
import { HStack, Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ExpandableCardProps = {
  /** Always-visible summary row — receives whether the card is currently expanded. */
  header: (expanded: boolean) => ReactNode;
  /** Detail content, only mounted (and animated in) while expanded. */
  children: ReactNode;
  defaultExpanded?: boolean;
  accessibilityLabel: string;
};

/** One category/bill as its own tappable card instead of a flat list row —
 * built for screens with too many budget lines to show fully expanded at
 * once (see budget/index.tsx's Fixed/Variable budget sections). Detail
 * content unmounts on collapse rather than height-animating, so it fades
 * in fresh via useEntrance every time it opens — cheap and consistent with
 * the rest of the app's motion language, no manual height measurement. */
export function ExpandableCard({ header, children, defaultExpanded = false, accessibilityLabel }: ExpandableCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const entranceStyle = useEntrance(0);

  return (
    <Card>
      <Stack gap={3}>
        <PressableScale
          onPress={() => setExpanded((e) => !e)}
          accessibilityRole="button"
          accessibilityLabel={accessibilityLabel}
          accessibilityState={{ expanded }}
        >
          <HeaderRow expanded={expanded}>{header(expanded)}</HeaderRow>
        </PressableScale>
        {expanded ? (
          <Animated.View style={entranceStyle}>
            <Stack gap={3}>{children}</Stack>
          </Animated.View>
        ) : null}
      </Stack>
    </Card>
  );
}

function HeaderRow({ expanded, children }: { expanded: boolean; children: ReactNode }) {
  const theme = useTheme();
  return (
    <HStack align="center" justify="space-between" gap={3}>
      <Stack flex={1}>{children}</Stack>
      <Animated.View style={{ transform: [{ rotate: expanded ? "180deg" : "0deg" }] }}>
        <CaretDown size={14} color={theme.colors.neutral[500]} weight="bold" />
      </Animated.View>
    </HStack>
  );
}
