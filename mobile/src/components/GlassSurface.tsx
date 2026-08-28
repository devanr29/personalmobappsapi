// Shared glass-material wrapper. On iOS 26+ this renders Apple's Liquid
// Glass via the native ExpoGlassEffect module; everywhere else
// expo-glass-effect's own GlassView degrades to a plain RN View
// (node_modules/expo-glass-effect/build/GlassView.js — no platform branch
// needed here, the library handles it). We always supply `backgroundColor`
// via `theme.glassFallback` so that degraded case still reads as an
// intentional solid surface instead of an invisible/unstyled view.
//
// Caveat (documented by the library): setting opacity to 0 on a GlassView
// stops the glass effect from rendering at all — never animate this
// component's opacity for enter/exit; animate a plain sibling View instead.
import { GlassView, type GlassStyle } from "expo-glass-effect";
import type { ReactNode } from "react";
import type { StyleProp, ViewStyle } from "react-native";

import { useTheme } from "@/theme/ThemeProvider";

export interface GlassSurfaceProps {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  glassStyle?: GlassStyle;
  /** Tint the glass material with the current accent color. */
  tinted?: boolean;
  interactive?: boolean;
}

export function GlassSurface({ children, style, glassStyle = "regular", tinted, interactive }: GlassSurfaceProps) {
  const theme = useTheme();

  return (
    <GlassView
      glassEffectStyle={glassStyle}
      tintColor={tinted ? theme.colors.accent : undefined}
      isInteractive={interactive}
      // Nocturne has no light mode — always request the dark glass
      // appearance regardless of system setting.
      colorScheme="dark"
      style={[{ backgroundColor: theme.glassFallback }, style]}
    >
      {children}
    </GlassView>
  );
}
