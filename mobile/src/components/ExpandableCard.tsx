import { useState, type ReactNode } from "react";
import Animated, { useReducedMotion } from "react-native-reanimated";
import { CaretDown } from "phosphor-react-native";

import { caretStyle, disclosure, PressableScale } from "@/theme/motion";
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
 * content mounts on expand and unmounts on collapse, fading in/out, while
 * the card's surface grows/shrinks on a layout transition and the cards
 * below slide (they carry the same transition) — no manual height
 * measurement. The surface is drawn here rather than via <Card> because the
 * view that animates its frame has to be the one painting the background.
 * Two layers: the outer one casts the shadow, the inner one clips the
 * detail content to the animating frame (overflow: hidden on the shadow
 * layer would clip the iOS shadow). */
export function ExpandableCard({ header, children, defaultExpanded = false, accessibilityLabel }: ExpandableCardProps) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Animated.View
      layout={disclosure.layoutTransition}
      style={{ borderRadius: theme.radius.md, backgroundColor: theme.colors.surface, ...theme.elevation.sm }}
    >
      <Animated.View
        layout={disclosure.layoutTransition}
        style={{ borderRadius: theme.radius.md, overflow: "hidden", padding: theme.spacing[4], gap: theme.spacing[3] }}
      >
        <PressableScale
          onPress={() => setExpanded((e) => !e)}
          accessibilityRole="button"
          accessibilityLabel={accessibilityLabel}
          accessibilityState={{ expanded }}
        >
          <HeaderRow expanded={expanded}>{header(expanded)}</HeaderRow>
        </PressableScale>
        {expanded ? (
          <Animated.View entering={disclosure.entering} exiting={disclosure.exiting}>
            <Stack gap={3}>{children}</Stack>
          </Animated.View>
        ) : null}
      </Animated.View>
    </Animated.View>
  );
}

function HeaderRow({ expanded, children }: { expanded: boolean; children: ReactNode }) {
  const theme = useTheme();
  const reduced = useReducedMotion();
  return (
    <HStack align="center" justify="space-between" gap={3}>
      <Stack flex={1}>{children}</Stack>
      <Animated.View style={caretStyle(expanded, reduced)}>
        <CaretDown size={14} color={theme.colors.neutral[500]} weight="bold" />
      </Animated.View>
    </HStack>
  );
}
