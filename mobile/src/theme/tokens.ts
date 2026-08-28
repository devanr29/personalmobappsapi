// Nocturne v2 dark design system — concrete resolved tokens.
// Spacing is a real 4pt grid (v1's 0.70x scale never matched the shipped
// design and was dead code); type roles are complete RN TextStyle objects
// so a component never has to hand-assemble fontFamily/lineHeight/letterSpacing.
import type { TextStyle } from "react-native";

export const neutral = {
  100: "#f3f5fe",
  200: "#e4e7f5",
  300: "#cfd3e5",
  400: "#b2b6ca",
  500: "#9397ab",
  600: "#75798c",
  700: "#595d6c",
  800: "#3f424d",
  900: "#292b31",
} as const;

export const accentRamp = {
  100: "#f5f4ff",
  200: "#e7e5fe",
  300: "#d2cefd",
  400: "#b5abfc",
  500: "#968ae0",
  600: "#796cbf",
  700: "#5d5294",
  800: "#423a6a",
  900: "#2b2741",
} as const;

export const colors = {
  text: "#e9e9ed",
  divider: "rgba(233,233,237,0.16)",
  positive: "#4ea87a",
  negative: "#d98c8c",
  // "tight" budget status — validated separately from categorical slots so it
  // never impersonates a chart series (see chart tokens below).
  tight: "#d9a441",
  defaultAccent: "#9184d9",
} as const;

export type GroundPresetName = "Midnight" | "Deep indigo" | "Slate";

export const groundPresets: Record<GroundPresetName, { bg: string; surface: string }> = {
  Midnight: { bg: "#161826", surface: "#232532" },
  "Deep indigo": { bg: "#191c3a", surface: "#262a4e" },
  Slate: { bg: "#191b20", surface: "#26282f" },
};

export type CornerPresetName = "Rounded" | "Crisp";

export const cornerPresets: Record<CornerPresetName, { lg: number; md: number; sm: number }> = {
  Rounded: { lg: 14, md: 8, sm: 4 },
  Crisp: { lg: 4, md: 3, sm: 2 },
};

// Fixed radii independent of the corner preset (per design spec).
export const radius = {
  pill: 22,
  full: 9999, // avatars / FAB (50%)
} as const;

// 4pt grid. Replaces the v1 0.70x scale (2.8/5.6/8.4/11.2/16.8/22.4), which
// never contained the design's real values (16px screen padding, 14-15px
// card padding, 16px gaps) and was used exactly once in the whole app.
export const spacing = {
  0: 0,
  px: 1,
  0.5: 2,
  1: 4,
  1.5: 6,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
} as const;

export type SpacingKey = keyof typeof spacing;

export const elevation = {
  // Dark-ground elevation is a hairline edge + ambient shadow, never a heavy
  // drop shadow (Nocturne rule) — sm stays edge-only, md adds a soft glow,
  // lg is for glass-backed floating chrome (sheets, floating headers).
  sm: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0,
    shadowRadius: 0,
    elevation: 0,
    borderWidth: 1,
    borderColor: neutral[800],
  },
  md: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.55,
    shadowRadius: 18,
    elevation: 6,
    borderWidth: 1,
    borderColor: neutral[700],
  },
  lg: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.6,
    shadowRadius: 28,
    elevation: 10,
    borderWidth: 1,
    borderColor: neutral[700],
  },
} as const;

export const fontFamily = {
  regular: "Inter_400Regular",
  medium: "Inter_500Medium",
  semiBold: "Inter_600SemiBold",
  bold: "Inter_700Bold",
} as const;

// Every role is a complete TextStyle — fontFamily + fontSize + lineHeight +
// letterSpacing where it matters — so `<Text variant="body">` never needs a
// second prop bolted on. (v1's roles carried only fontSize/fontWeight, which
// is why every call site had to hand-assemble the rest and mostly didn't bother.)
export const type: Record<
  "display" | "bigNumber" | "title" | "heading" | "cardTitle" | "bodyStrong" | "body" | "label" | "meta" | "caption" | "tabLabel",
  TextStyle
> = {
  display: { fontFamily: fontFamily.medium, fontSize: 32, lineHeight: 36, letterSpacing: -0.02 * 32 },
  bigNumber: { fontFamily: fontFamily.medium, fontSize: 27, lineHeight: 31, letterSpacing: -0.02 * 27 },
  title: { fontFamily: fontFamily.medium, fontSize: 23, lineHeight: 26, letterSpacing: -0.015 * 23 },
  heading: { fontFamily: fontFamily.medium, fontSize: 17, lineHeight: 22 },
  cardTitle: { fontFamily: fontFamily.medium, fontSize: 15, lineHeight: 20 },
  bodyStrong: { fontFamily: fontFamily.medium, fontSize: 14, lineHeight: 20 },
  body: { fontFamily: fontFamily.regular, fontSize: 14, lineHeight: 20 },
  label: { fontFamily: fontFamily.regular, fontSize: 13, lineHeight: 18 },
  meta: { fontFamily: fontFamily.regular, fontSize: 12, lineHeight: 16 },
  caption: { fontFamily: fontFamily.regular, fontSize: 11, lineHeight: 14 },
  tabLabel: { fontFamily: fontFamily.medium, fontSize: 10.5, lineHeight: 13 },
};

// Tabular-figure variants for every role that renders an IDR amount, so
// 7-digit Rupiah values don't jitter width on re-render (count-up, live
// budget updates).
const numericRoles = ["display", "bigNumber", "body", "bodyStrong", "label", "meta"] as const;
export const numericType: Record<(typeof numericRoles)[number], TextStyle> = Object.fromEntries(
  numericRoles.map((role) => [role, { ...type[role], fontVariant: ["tabular-nums"] }]),
) as Record<(typeof numericRoles)[number], TextStyle>;

export const motion = {
  duration: {
    instant: 0,
    fast: 140,
    base: 220,
    slow: 360,
    deliberate: 600,
  },
  // Cubic-bezier control points (framework-agnostic — consumed by both
  // Reanimated's Easing.bezier and RN Animated's Easing.bezier).
  easing: {
    standard: [0.4, 0, 0.2, 1],
    decelerate: [0, 0, 0.2, 1],
    accelerate: [0.4, 0, 1, 1],
  },
  spring: { damping: 18, stiffness: 220, mass: 0.9 },
  // ms delay per item for staggered list entrance; caps around 8 items.
  staggerStep: 40,
  staggerCap: 8,
} as const;

// Chart palette — computed and validated (OKLCH lightness band, chroma
// floor, Machado 2009 CVD deltaE, WCAG contrast) against all three ground
// presets, not chosen by eye. See plan doc for the validator runs.
//
// A 3+-slot categorical set is not achievable on Nocturne: the accent is
// blue-violet, so every cyan/teal candidate collapses against it under
// deuteranopia. Sequential (one hue, the accent ramp) is the workhorse;
// categorical is capped at 2 slots.
// Curated, contrast-validated (WCAG >= 4.5:1 on all 3 ground presets)
// accent choices for the Settings screen. Deliberately excludes amber-ish
// hues: the chart system's fixed categorical secondary is
// chart.categoricalSecondary (#bd8a35) below, and an amber accent would
// make the accent-vs-deductions pair in every budget chart indistinguishable.
export const accentOptions = [
  { name: "Blurple", hex: "#9184d9" },
  { name: "Rose", hex: "#d97a9c" },
  { name: "Teal", hex: "#4fb7ab" },
  { name: "Sky", hex: "#6fa8dc" },
  { name: "Green", hex: "#7ab876" },
] as const;

export const chart = {
  // accentRamp 300->700, monotone lightness, single hue — passes the
  // ordinal/sequential validator outright.
  sequential: [accentRamp[300], accentRamp[400], accentRamp[500], accentRamp[600], accentRamp[700]] as const,
  // second categorical slot (first slot is the dynamic accent, composed in
  // ThemeProvider). CVD deltaE 23.4 deutan / 23.2 normal vs accent, >=3:1 on
  // all three grounds.
  categoricalSecondary: "#bd8a35",
  track: neutral[800],
  axis: neutral[800],
} as const;
