// RN Text can't have its children driven by useAnimatedStyle (that only
// patches style props, not children) — so the count-up runs as a Reanimated
// timing on a shared value, mirrored into React state via useAnimatedReaction
// only when the rounded Rupiah amount actually changes.
import { useEffect, useState } from "react";
import { runOnJS, useAnimatedReaction, useSharedValue, withTiming } from "react-native-reanimated";

import { Text, type TextProps } from "@/theme/primitives";
import { easing } from "@/theme/motion";
import { motion } from "@/theme/tokens";
import { formatRupiah } from "@/utils/currency";

export interface AnimatedCurrencyProps extends Omit<TextProps, "children" | "numeric"> {
  value: number;
  durationMs?: number;
}

export function AnimatedCurrency({ value, durationMs = motion.duration.slow, ...textProps }: AnimatedCurrencyProps) {
  const progress = useSharedValue(0);
  const [display, setDisplay] = useState(() => formatRupiah(value));
  const setDisplayFromValue = (n: number) => setDisplay(formatRupiah(n));

  useEffect(() => {
    progress.value = withTiming(value, { duration: durationMs, easing: easing.decelerate });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useAnimatedReaction(
    () => Math.round(progress.value),
    (current, previous) => {
      if (current !== previous) {
        // formatRupiah is a plain JS function, not a worklet — it must run
        // inside the runOnJS callback (JS thread), not be called on the UI
        // thread and have only its result handed across the bridge.
        runOnJS(setDisplayFromValue)(current);
      }
    },
  );

  return (
    <Text numeric {...textProps}>
      {display}
    </Text>
  );
}
