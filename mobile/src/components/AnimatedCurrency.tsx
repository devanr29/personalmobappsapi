// Count-up for live IDR figures, run entirely on the UI thread. RN Text
// can't have its content driven by a shared value, so this renders a
// non-editable TextInput styled exactly like <Text> and patches its `text`
// prop from useAnimatedProps every frame — React never re-renders while the
// number ticks (the old version mirrored every rounded value into React
// state via runOnJS, one render per frame).
//
// Can't be nested inside a <Text> (it's a TextInput); inline amounts in a
// sentence use formatRupiah directly.
import { useEffect } from "react";
import { TextInput, type StyleProp, type TextStyle } from "react-native";
import Animated, { useAnimatedProps, useReducedMotion, useSharedValue, withTiming } from "react-native-reanimated";

import { easing } from "@/theme/motion";
import { textStyle, type Tone, type TypeVariant } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { motion } from "@/theme/tokens";
import { formatRupiah, formatRupiahWorklet } from "@/utils/currency";

const AnimatedTextInput = Animated.createAnimatedComponent(TextInput);

export interface AnimatedCurrencyProps {
  value: number;
  variant?: TypeVariant;
  tone?: Tone;
  style?: StyleProp<TextStyle>;
  durationMs?: number;
}

export function AnimatedCurrency({ value, variant, tone, style, durationMs = motion.duration.slow }: AnimatedCurrencyProps) {
  const theme = useTheme();
  const reduced = useReducedMotion();
  // Counts up from 0 on first mount, then from the previous value on change.
  const shown = useSharedValue(reduced ? value : 0);

  useEffect(() => {
    shown.set(reduced ? value : withTiming(value, { duration: durationMs, easing: easing.decelerate }));
  }, [value, durationMs, reduced, shown]);

  const animatedProps = useAnimatedProps(() => {
    const text = formatRupiahWorklet(shown.get());
    // `text` isn't in TextInput's public props but is what the native view
    // reads; defaultValue keeps it in sync if the view re-mounts.
    return { text, defaultValue: text } as object;
  });

  return (
    <AnimatedTextInput
      editable={false}
      scrollEnabled={false}
      underlineColorAndroid="transparent"
      defaultValue={formatRupiah(reduced ? value : 0)}
      animatedProps={animatedProps}
      accessibilityRole="text"
      accessibilityLabel={formatRupiah(value)}
      style={[
        textStyle(theme, variant, tone, true),
        { padding: theme.spacing[0], margin: theme.spacing[0], includeFontPadding: false, pointerEvents: "none" },
        style,
      ]}
    />
  );
}
