import type { ReactNode } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, View, type DimensionValue } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { GlassSurface } from "@/components/GlassSurface";
import { useTheme } from "@/theme/ThemeProvider";

export type BottomSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Blocks backdrop taps and the Android back button, e.g. mid-submit. */
  dismissDisabled?: boolean;
  /** Fired once the sheet has finished its exit animation (iOS only, see
   * Modal's onDismiss) — the point where another Modal can safely present. */
  onDismiss?: () => void;
  maxHeight?: DimensionValue;
  children: ReactNode;
};

/** The one bottom-sheet frame every sheet in the app sits in, so the three
 * things each sheet used to get individually wrong live in one place:
 *
 *  - KeyboardAvoidingView owns the full-screen flex box (not nested inside
 *    the flex-end backdrop), so the sheet actually rises with the keyboard
 *    instead of re-anchoring behind it.
 *  - The glass extends to the screen edge but its content is padded above
 *    the home indicator / gesture bar (insets.bottom).
 *  - Tapping the dimmed backdrop dismisses, like a native sheet. */
export function BottomSheet({ visible, onClose, dismissDisabled = false, onDismiss, maxHeight = "90%", children }: BottomSheetProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const close = dismissDisabled ? undefined : onClose;

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={close} onDismiss={onDismiss}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <Pressable
            style={[StyleSheet.absoluteFill, { backgroundColor: "rgba(0,0,0,0.5)" }]}
            onPress={close}
            accessibilityRole="button"
            accessibilityLabel="Dismiss"
          />
          <GlassSurface
            style={{
              borderTopLeftRadius: theme.radius.lg,
              borderTopRightRadius: theme.radius.lg,
              overflow: "hidden",
              maxHeight,
              paddingBottom: insets.bottom,
            }}
          >
            {children}
          </GlassSurface>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
