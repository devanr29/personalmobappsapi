import * as Haptics from "expo-haptics";
import { CheckCircle, CircleIcon } from "phosphor-react-native";
import { useEffect, useRef } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withTiming } from "react-native-reanimated";

import { easing } from "@/theme/motion";
import { useTheme } from "@/theme/ThemeProvider";
import { motion } from "@/theme/tokens";

const ICON_SIZE = 16;
const PULSE_DURATION = 450;

/** The paid/unpaid mark on a bill or variable category card. When it flips
 * to paid while visible — the card is expanded, so the user just did it —
 * the check settles in from 0.9 and a ring pulses out behind it, with a
 * success haptic in the same commit. It stays quiet on mount (expanding an
 * already-paid card) and when flipping back to unpaid.
 *
 * Reduce Motion: no scale or ring; the icon/color swap and haptic remain. */
export function PaidCheck({ paid, pending }: { paid: boolean; pending: boolean }) {
  const theme = useTheme();
  const reduced = useReducedMotion();
  const wasPaid = useRef(paid);
  const scale = useSharedValue(1);
  const pulse = useSharedValue(1); // 0 → 1 over the pulse; 1 = at rest (invisible)

  useEffect(() => {
    if (paid && !wasPaid.current) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      if (!reduced) {
        scale.set(0.9);
        scale.set(withTiming(1, { duration: motion.duration.base, easing: easing.out }));
        pulse.set(0);
        pulse.set(withTiming(1, { duration: PULSE_DURATION, easing: easing.out }));
      }
    }
    wasPaid.current = paid;
  }, [paid, reduced, scale, pulse]);

  const iconStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  const ringStyle = useAnimatedStyle(() => ({
    opacity: (1 - pulse.get()) * 0.5,
    transform: [{ scale: 1 + pulse.get() * 1.2 }],
  }));

  if (pending) return <ActivityIndicator size="small" color={theme.colors.accent} />;

  return (
    <View style={{ width: ICON_SIZE, height: ICON_SIZE }}>
      <Animated.View
        style={[StyleSheet.absoluteFill, { borderRadius: theme.radius.full, backgroundColor: theme.status.comfortable }, ringStyle]}
      />
      <Animated.View style={iconStyle}>
        {paid ? (
          <CheckCircle size={ICON_SIZE} color={theme.status.comfortable} weight="fill" />
        ) : (
          <CircleIcon size={ICON_SIZE} color={theme.colors.neutral[500]} />
        )}
      </Animated.View>
    </View>
  );
}
