// Single-ratio meter — the workhorse form for anything "how much of a limit"
// (budget category spent/remaining, search relevance, runway to payday).
// Fill is square at the baseline (origin) and rounded at the data-end, per
// the bar mark spec. Overspend must never render past 100% — callers pass
// already-clamped business values, but this clamps again defensively so a
// chart can never visually claim negative-remaining as a filled bar.
import { useEffect } from "react";
import { View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";

import { clamp01, mark } from "./geometry";
import { easing } from "@/theme/motion";
import { useTheme } from "@/theme/ThemeProvider";

export interface MeterProps {
  /** 0..1 — clamped defensively; overspend must be pre-clamped by the caller too. */
  value: number;
  color?: string;
  trackColor?: string;
  thickness?: number;
}

export function Meter({ value, color, trackColor, thickness = mark.barThickness }: MeterProps) {
  const theme = useTheme();
  const target = clamp01(value);
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(target, { duration: theme.motion.duration.slow, easing: easing.decelerate });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  const fillStyle = useAnimatedStyle(() => ({ width: `${progress.value * 100}%` }));

  return (
    <View
      style={{
        height: thickness,
        borderRadius: mark.barEndRadius,
        backgroundColor: trackColor ?? theme.chart.track,
        overflow: "hidden",
      }}
    >
      <Animated.View
        style={[
          {
            height: "100%",
            backgroundColor: color ?? theme.colors.accent,
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
            borderTopRightRadius: mark.barEndRadius,
            borderBottomRightRadius: mark.barEndRadius,
          },
          fillStyle,
        ]}
      />
    </View>
  );
}
