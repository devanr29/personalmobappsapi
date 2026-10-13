import * as Haptics from "expo-haptics";
import { useEffect, useState, type ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  View,
  useWindowDimensions,
  type DimensionValue,
} from "react-native";
import { Gesture, GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { scheduleOnRN } from "react-native-worklets";

import { GlassSurface } from "@/components/GlassSurface";
import { easing } from "@/theme/motion";
import { useTheme } from "@/theme/ThemeProvider";
import { motion } from "@/theme/tokens";

export type BottomSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Blocks backdrop taps, the drag handle and the Android back button, e.g. mid-submit. */
  dismissDisabled?: boolean;
  /** Fired once the sheet has finished its exit animation (iOS only, see
   * Modal's onDismiss) — the point where another Modal can safely present. */
  onDismiss?: () => void;
  maxHeight?: DimensionValue;
  children: ReactNode;
};

// Programmatic open: no finger involved, so no overshoot.
const OPEN_SPRING = { duration: 300, dampingRatio: 1 } as const;
// Snap back after a drag that didn't dismiss: carries the finger's velocity.
const SNAP_SPRING = { duration: 300, dampingRatio: 0.8 } as const;
// A flick this fast (px/s, downward) dismisses regardless of distance.
const DISMISS_VELOCITY = 800;
// ...or a drag past this fraction of the sheet's height, unless the finger
// was moving back up when it let go.
const DISMISS_DISTANCE = 0.3;
const CANCEL_VELOCITY = -300;

/** The one bottom-sheet frame every sheet in the app sits in:
 *
 *  - KeyboardAvoidingView owns the full-screen flex box (not nested inside
 *    the flex-end backdrop), so the sheet actually rises with the keyboard
 *    instead of re-anchoring behind it.
 *  - The glass extends to the screen edge but its content is padded above
 *    the home indicator / gesture bar (insets.bottom).
 *  - Tapping the dimmed backdrop dismisses, like a native sheet.
 *  - Motion is driven here rather than by Modal's own "slide": the sheet
 *    rises on a spring while the backdrop fades (instead of sliding up with
 *    it), and the grabber strip drags it — a flick or a long enough pull
 *    dismisses, anything else springs back with the finger's velocity.
 *    Only the strip is draggable so it never fights a ScrollView inside.
 *  - The glass runs OVERDRAG past the bottom edge, so pulling up past rest
 *    (rubber-banded) never shows a gap under it.
 *
 * Reduce Motion: the sheet appears and disappears in place and only the
 * backdrop fades; dragging still tracks the finger. */
export function BottomSheet({ visible, onClose, dismissDisabled = false, onDismiss, maxHeight = "90%", children }: BottomSheetProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const reduced = useReducedMotion();
  const { height: windowHeight } = useWindowDimensions();
  const close = dismissDisabled ? undefined : onClose;
  const overdrag = theme.spacing[12];

  // The Modal stays mounted through the exit animation and unmounts when it
  // finishes; render-phase adjustment so opening never waits a frame.
  const [mounted, setMounted] = useState(visible);
  if (visible && !mounted) setMounted(true);
  if (!visible && mounted && reduced) setMounted(false);

  const progress = useSharedValue(0); // 0 = closed, 1 = open
  const drag = useSharedValue(0); // finger offset from rest, px (down = +)
  const dragStart = useSharedValue(0);
  const sheetHeight = useSharedValue(windowHeight);

  useEffect(() => {
    if (visible) {
      if (!mounted) return;
      drag.set(0);
      progress.set(reduced ? withTiming(1, { duration: motion.duration.fast, easing: easing.out }) : withSpring(1, OPEN_SPRING));
    } else if (reduced) {
      progress.set(0);
    } else {
      progress.set(
        withTiming(0, { duration: motion.duration.base, easing: easing.out }, (finished) => {
          if (finished) scheduleOnRN(setMounted, false);
        }),
      );
    }
  }, [visible, mounted, reduced, progress, drag]);

  const dismissFromDrag = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    onClose();
  };

  const pan = Gesture.Pan()
    .enabled(!dismissDisabled)
    .activeOffsetY([-6, 6])
    .hitSlop({ bottom: theme.spacing[2] })
    .onStart(() => {
      cancelAnimation(drag);
      dragStart.set(drag.get());
    })
    .onUpdate((e) => {
      const raw = dragStart.get() + e.translationY;
      // Down tracks the finger 1:1; up is rubber-banded toward OVERDRAG.
      drag.set(raw >= 0 ? raw : -overdrag * (1 - 1 / (1 + (-raw * 0.55) / overdrag)));
    })
    .onEnd((e) => {
      const dragged = drag.get();
      const shouldDismiss =
        e.velocityY > DISMISS_VELOCITY || (dragged > sheetHeight.get() * DISMISS_DISTANCE && e.velocityY > CANCEL_VELOCITY);
      if (shouldDismiss) {
        drag.set(withSpring(sheetHeight.get(), { ...OPEN_SPRING, velocity: e.velocityY, overshootClamping: true }));
        scheduleOnRN(dismissFromDrag);
      } else {
        drag.set(withSpring(0, { ...SNAP_SPRING, velocity: e.velocityY }));
      }
    });

  const backdropStyle = useAnimatedStyle(() => {
    const dragFraction = Math.min(Math.max(drag.get() / sheetHeight.get(), 0), 1);
    return { opacity: progress.get() * (1 - dragFraction) };
  });

  const sheetStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: (reduced ? 0 : (1 - progress.get()) * sheetHeight.get()) + drag.get() }],
  }));

  return (
    <Modal visible={mounted} animationType="none" transparent onRequestClose={close} onDismiss={onDismiss}>
      {/* Android Modals render outside the app's GestureHandlerRootView. */}
      <GestureHandlerRootView style={{ flex: 1 }}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <View style={{ flex: 1, justifyContent: "flex-end", pointerEvents: visible ? "box-none" : "none" }}>
            <Animated.View style={[StyleSheet.absoluteFill, backdropStyle]}>
              <Pressable
                style={[StyleSheet.absoluteFill, { backgroundColor: "rgba(0,0,0,0.5)" }]}
                onPress={close}
                accessibilityRole="button"
                accessibilityLabel="Dismiss"
              />
            </Animated.View>
            <Animated.View
              style={[{ maxHeight, marginBottom: -overdrag }, sheetStyle]}
              onLayout={(e) => sheetHeight.set(e.nativeEvent.layout.height)}
            >
              <GlassSurface
                style={{
                  flexShrink: 1,
                  borderTopLeftRadius: theme.radius.lg,
                  borderTopRightRadius: theme.radius.lg,
                  overflow: "hidden",
                  paddingBottom: insets.bottom + overdrag,
                }}
              >
                <GestureDetector gesture={pan}>
                  <View
                    style={{ alignItems: "center", paddingTop: theme.spacing[3], paddingBottom: theme.spacing[2] }}
                    accessible={false}
                  >
                    <View
                      style={{
                        width: theme.spacing[10],
                        height: theme.spacing[1],
                        borderRadius: theme.radius.full,
                        backgroundColor: theme.colors.neutral[600],
                      }}
                    />
                  </View>
                </GestureDetector>
                {children}
              </GlassSurface>
            </Animated.View>
          </View>
        </KeyboardAvoidingView>
      </GestureHandlerRootView>
    </Modal>
  );
}
