// Motion system built on Reanimated 4.5 (already a direct dependency).
// Pairs with the duration/easing/spring/stagger values in tokens.ts so every
// animation in the app pulls from the same handful of curves instead of each
// screen inventing its own.
import * as Haptics from "expo-haptics";
import type { ReactNode } from "react";
import { useEffect } from "react";
import type { PressableProps, StyleProp, ViewStyle } from "react-native";
import { Pressable } from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withSpring,
  withTiming,
  type SharedValue,
} from "react-native-reanimated";

import { motion as motionTokens } from "./tokens";

const bezier = (points: readonly [number, number, number, number]) => Easing.bezier(points[0], points[1], points[2], points[3]);

export const easing = {
  standard: bezier(motionTokens.easing.standard as [number, number, number, number]),
  decelerate: bezier(motionTokens.easing.decelerate as [number, number, number, number]),
  accelerate: bezier(motionTokens.easing.accelerate as [number, number, number, number]),
};

/**
 * Fade + rise entrance for a single item. Pass a list index to stagger it —
 * delay is capped at `motion.staggerCap` items so long lists don't take
 * seconds to finish animating in.
 */
export function useEntrance(index = 0) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(8);

  useEffect(() => {
    const delay = Math.min(index, motionTokens.staggerCap) * motionTokens.staggerStep;
    opacity.value = withDelay(delay, withTiming(1, { duration: motionTokens.duration.base, easing: easing.decelerate }));
    translateY.value = withDelay(delay, withTiming(0, { duration: motionTokens.duration.base, easing: easing.decelerate }));
    // Intentionally re-runs only when the item's position changes, not on
    // every parent re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  return useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));
}

/** Raw press-scale shared value + handlers, for components that need the
 *  animated style merged into a larger style array. */
export function usePressScale(target = 0.97) {
  const scale = useSharedValue(1);

  const onPressIn = () => {
    scale.value = withTiming(target, { duration: motionTokens.duration.fast, easing: easing.standard });
  };
  const onPressOut = () => {
    scale.value = withSpring(1, motionTokens.spring);
  };

  const style = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  return { style, onPressIn, onPressOut };
}

export interface PressableScaleProps extends PressableProps {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  scaleTo?: number;
}

/**
 * Drop-in replacement for RN's `Pressable` that adds the standard 0.97
 * press-scale feedback plus a light haptic tap — the default way to write
 * anything pressable in this app.
 */
export function PressableScale({ children, style, scaleTo, disabled, onPressIn, onPressOut, ...rest }: PressableScaleProps) {
  const { style: animatedStyle, onPressIn: startPress, onPressOut: endPress } = usePressScale(scaleTo);

  return (
    <AnimatedPressable
      disabled={disabled}
      onPressIn={(e) => {
        startPress();
        if (!disabled) {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        }
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        endPress();
        onPressOut?.(e);
      }}
      style={[animatedStyle, style]}
      {...rest}
    >
      {children}
    </AnimatedPressable>
  );
}

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export interface AnimatedListItemProps {
  index: number;
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}

/**
 * Wraps one list row so it can call `useEntrance` on its own render — a
 * component instance per item, not a hook called inside `.map()`, so this
 * stays valid even as the list's length changes between renders.
 */
export function AnimatedListItem({ index, children, style }: AnimatedListItemProps) {
  const entranceStyle = useEntrance(index);
  return <Animated.View style={[entranceStyle, style]}>{children}</Animated.View>;
}

/** Raw animated shared value driving toward `target` — pair with an
 *  `AnimatedCurrency`/`AnimatedNumber` display component (built alongside
 *  the screens that render live IDR figures) rather than plain RN Text,
 *  which can't subscribe to a Reanimated shared value directly. */
export function useCountUp(target: number, durationMs: number = motionTokens.duration.slow): SharedValue<number> {
  const value = useSharedValue(target === 0 ? 0 : 0);

  useEffect(() => {
    value.value = withTiming(target, { duration: durationMs, easing: easing.decelerate });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return value;
}
