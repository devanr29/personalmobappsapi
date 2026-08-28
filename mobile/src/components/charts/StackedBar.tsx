// Part-to-whole composition bar (e.g. free money vs total deductions).
// Categorical — capped at 2 segments per the validated Nocturne chart
// palette (see theme/tokens.ts chart.categorical; a 3rd hue fails CVD
// separation against the accent on every ground preset). Segments are
// separated by a surface-color gap, never a stroke.
import type { ReactNode } from "react";
import { View } from "react-native";

import { clamp01, mark } from "./geometry";
import { useTheme } from "@/theme/ThemeProvider";

export interface StackedBarSegment {
  value: number;
  color: string;
}

export interface StackedBarProps {
  segments: StackedBarSegment[];
  /** Denominator; defaults to the sum of segment values. */
  total?: number;
  trackColor?: string;
  thickness?: number;
}

export function StackedBar({ segments, total, trackColor, thickness = mark.barThickness }: StackedBarProps): ReactNode {
  const theme = useTheme();
  const sum = segments.reduce((acc, s) => acc + Math.max(0, s.value), 0);
  const denom = (total ?? sum) || 1;

  const firstVisible = segments.findIndex((s) => s.value > 0);
  let lastVisible = -1;
  segments.forEach((s, i) => {
    if (s.value > 0) lastVisible = i;
  });

  return (
    <View
      style={{
        flexDirection: "row",
        height: thickness,
        borderRadius: mark.barEndRadius,
        overflow: "hidden",
        backgroundColor: trackColor ?? theme.chart.track,
      }}
    >
      {segments.map((seg, i) => {
        const pct = clamp01(Math.max(0, seg.value) / denom);
        if (pct <= 0) return null;
        const isFirst = i === firstVisible;
        const isLast = i === lastVisible;
        return (
          <View
            key={i}
            style={{
              width: `${pct * 100}%`,
              height: "100%",
              backgroundColor: seg.color,
              marginRight: isLast ? 0 : mark.surfaceGap,
              borderTopLeftRadius: isFirst ? mark.barEndRadius : 0,
              borderBottomLeftRadius: isFirst ? mark.barEndRadius : 0,
              borderTopRightRadius: isLast ? mark.barEndRadius : 0,
              borderBottomRightRadius: isLast ? mark.barEndRadius : 0,
            }}
          />
        );
      })}
    </View>
  );
}
