// Before -> after on a single normalized axis (e.g. today -> due date within
// a pay cycle). Plain Views, not SVG — a straight horizontal connector
// between two percentage positions doesn't need a canvas.
import { View } from "react-native";

import { clamp01, mark } from "./geometry";
import { useTheme } from "@/theme/ThemeProvider";

export interface DumbbellProps {
  /** 0..1 normalized position of the origin point. */
  from: number;
  /** 0..1 normalized position of the emphasis point. */
  to: number;
  color?: string;
  baseColor?: string;
  height?: number;
}

export function Dumbbell({ from, to, color, baseColor, height = mark.markerMinDiameter }: DumbbellProps) {
  const theme = useTheme();
  const a = clamp01(from);
  const b = clamp01(to);
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  const emphasisColor = color ?? theme.colors.accent;
  const originColor = baseColor ?? theme.colors.neutral[600];
  const dotSize = mark.markerMinDiameter;

  return (
    <View style={{ height, justifyContent: "center" }}>
      <View
        style={{
          position: "absolute",
          left: `${lo * 100}%`,
          right: `${(1 - hi) * 100}%`,
          height: mark.lineWidth,
          borderRadius: mark.lineWidth / 2,
          backgroundColor: theme.chart.axis,
        }}
      />
      <View
        style={{
          position: "absolute",
          left: `${a * 100}%`,
          width: dotSize,
          height: dotSize,
          marginLeft: -dotSize / 2,
          borderRadius: dotSize / 2,
          backgroundColor: originColor,
        }}
      />
      <View
        style={{
          position: "absolute",
          left: `${b * 100}%`,
          width: dotSize,
          height: dotSize,
          marginLeft: -dotSize / 2,
          borderRadius: dotSize / 2,
          backgroundColor: emphasisColor,
        }}
      />
    </View>
  );
}
