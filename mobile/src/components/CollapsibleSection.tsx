import { useState, type ReactNode } from "react";
import Animated, { useReducedMotion } from "react-native-reanimated";
import { CaretDown, Plus } from "phosphor-react-native";

import { Card } from "@/components/Card";
import { caretStyle, disclosure, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type CollapsibleSectionProps = {
  title: string;
  /** Count/total line shown under the title, e.g. "6 items · Rp 2.059.900". */
  summary: string;
  addLabel: string;
  onAdd: () => void;
  children: ReactNode;
  defaultExpanded?: boolean;
};

/** A budget section (Fixed budget / Variable budget) collapsed behind one
 * summary card by default — the individual item cards it holds are their
 * own Cards too, so unlike ExpandableCard this doesn't nest a Card inside a
 * Card (surface-on-surface reads as one undifferentiated block). The header
 * card is tappable everywhere; the add action lives in the expanded body
 * instead of the header so it isn't a press target nested inside one.
 *
 * The body fades in/out on mount/unmount; the section root and the add row
 * carry the shared layout transition so they slide (along with the item
 * cards, which carry it too) when anything above them opens or closes. */
export function CollapsibleSection({ title, summary, addLabel, onAdd, children, defaultExpanded = false }: CollapsibleSectionProps) {
  const theme = useTheme();
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Animated.View layout={disclosure.layoutTransition} style={{ gap: theme.spacing[3] }}>
      <PressableScale
        onPress={() => setExpanded((e) => !e)}
        accessibilityRole="button"
        accessibilityLabel={`${title}, ${summary}`}
        accessibilityState={{ expanded }}
      >
        <Card>
          <HStack align="center" justify="space-between" gap={3}>
            <Stack gap={0.5} flex={1}>
              <Text variant="heading">{title}</Text>
              <Text variant="caption" tone="muted">
                {summary}
              </Text>
            </Stack>
            <Animated.View style={caretStyle(expanded, reduced)}>
              <CaretDown size={14} color={theme.colors.neutral[500]} weight="bold" />
            </Animated.View>
          </HStack>
        </Card>
      </PressableScale>
      {expanded ? (
        <Animated.View entering={disclosure.entering} exiting={disclosure.exiting} layout={disclosure.layoutTransition}>
          <Stack gap={3}>
            {children}
            <Animated.View layout={disclosure.layoutTransition}>
              <PressableScale onPress={onAdd} accessibilityRole="button" accessibilityLabel={addLabel}>
                <HStack align="center" justify="center" gap={1.5} p={3} radius="md" bg={theme.colors.neutral[800]}>
                  <Plus size={16} color={theme.colors.accent} weight="bold" />
                  <Text variant="label" tone="accent">
                    {addLabel}
                  </Text>
                </HStack>
              </PressableScale>
            </Animated.View>
          </Stack>
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}
