// Nocturne v3 — light/dark design system imported from the "Nocturne.dc.html"
// Claude Design project (Nunito Sans, shadow-based elevation, colorful icon
// tiles). Supersedes v2's dark-only, hairline-only system. Spacing is a real
// 4pt grid; type roles are complete RN TextStyle objects so a component never
// has to hand-assemble fontFamily/lineHeight/letterSpacing.
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

export type NineStepRamp = {
  100: string; 200: string; 300: string; 400: string; 500: string;
  600: string; 700: string; 800: string; 900: string;
};

export type ElevationLevel = {
  shadowColor: string;
  shadowOffset: { width: number; height: number };
  shadowOpacity: number;
  shadowRadius: number;
  elevation: number;
  borderWidth: number;
};

export type TileTint = { bg: string; fg: string };

// Mirrors a 100..900 ramp end-for-end (100<->900, 200<->800, ... 500 stays
// put). Every call site that reads `neutral`/`accentRamp` picks two indices
// far apart for an fg/bg contrast pair (e.g. bg=900/fg=300) rather than
// relying on absolute lightness, so reversing the whole ramp turns a
// dark-native "light fg on dark fill" pair into a correct "dark fg on light
// fill" pair for the other theme with zero call-site changes. NOT used for
// chart.sequential, which has a fixed magnitude-order direction (low value =
// pale, high value = saturated) rather than a symmetric pairing — see chart
// below.
export function reverseRamp(ramp: NineStepRamp): NineStepRamp {
  return {
    100: ramp[900], 200: ramp[800], 300: ramp[700], 400: ramp[600],
    500: ramp[500],
    600: ramp[400], 700: ramp[300], 800: ramp[200], 900: ramp[100],
  };
}

// Scales an "#rrggbb" hex toward black by `factor` (0..1 per channel) — used
// to derive a light-mode-safe variant of a user-chosen accent that the
// design import only defines once, dark-native. A mechanical darken, not an
// OKLCH/CVD-validated color — see the dark accentOptions below for that bar.
export function darken(hex: string, factor: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.round(((n >> 16) & 255) * factor);
  const g = Math.round(((n >> 8) & 255) * factor);
  const b = Math.round((n & 255) * factor);
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

// Mode-native semantic colors that aren't part of either 9-step ramp —
// straight from the Nocturne.dc.html design import (txt/line/pos/neg/warn/acc).
export const darkColors = {
  text: "#f0f0f3",
  divider: "rgba(255,255,255,.08)",
  positive: "#4fbfa6",
  negative: "#f0906b",
  // "tight" budget status — validated separately from categorical slots so it
  // never impersonates a chart series (see chart tokens below).
  tight: "#e6bc5c",
  defaultAccent: "#8b8bf0",
} as const;

export const lightColors = {
  text: "#2a2b33",
  divider: "rgba(42,43,51,.07)",
  positive: "#2f9e8a",
  negative: "#e8734a",
  tight: "#d9a441",
  defaultAccent: "#5b5bd6",
} as const;

// Back-compat named export for call sites that need a color before a mode is
// known (SettingsProvider's default config) — pinned to dark.
export const colors = darkColors;

export type GroundPresetName = "Midnight" | "Deep indigo" | "Slate";

// Dark-mode-only ground customization (3 variants) — light mode has a single
// fixed ground per the design import, no equivalent picker. "Midnight" is
// the import's own dark ground; the other two predate it and are untouched.
export const groundPresets: Record<GroundPresetName, { bg: string; surface: string }> = {
  Midnight: { bg: "#14151a", surface: "#1d1f26" },
  "Deep indigo": { bg: "#191c3a", surface: "#262a4e" },
  Slate: { bg: "#191b20", surface: "#26282f" },
};

export const lightGround = { bg: "#f6f5f3", surface: "#ffffff" } as const;

export type CornerPresetName = "Rounded" | "Crisp";

export const cornerPresets: Record<CornerPresetName, { lg: number; md: number; sm: number }> = {
  Rounded: { lg: 16, md: 12, sm: 8 },
  Crisp: { lg: 6, md: 4, sm: 2 },
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

// Shadow-based elevation (design import's --sh / --floatsh), replacing v2's
// hairline-edge-only rule — cards now carry a real ambient shadow in both
// modes, heavier in light (needs more contrast against a near-white ground)
// than dark. sm = card-level (--sh); md/lg both map to the one "floating"
// tier (--floatsh) — nothing in the app currently needs a third distinct
// level between them.
export const elevationDark = {
  sm: { shadowColor: "#000000", shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.4, shadowRadius: 3, elevation: 2, borderWidth: 0 },
  md: { shadowColor: "#000000", shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.6, shadowRadius: 28, elevation: 12, borderWidth: 0 },
  lg: { shadowColor: "#000000", shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.6, shadowRadius: 28, elevation: 12, borderWidth: 0 },
} as const;

export const elevationLight = {
  sm: { shadowColor: "#1e202d", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 10, elevation: 2, borderWidth: 0 },
  md: { shadowColor: "#1e202d", shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.18, shadowRadius: 28, elevation: 8, borderWidth: 0 },
  lg: { shadowColor: "#1e202d", shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.18, shadowRadius: 28, elevation: 8, borderWidth: 0 },
} as const;

export const fontFamily = {
  regular: "NunitoSans_400Regular",
  medium: "NunitoSans_600SemiBold",
  semiBold: "NunitoSans_700Bold",
  bold: "NunitoSans_800ExtraBold",
} as const;

// Every role is a complete TextStyle — fontFamily + fontSize + lineHeight +
// letterSpacing where it matters — so `<Text variant="body">` never needs a
// second prop bolted on. Sizes/line-heights are unchanged from v2 (they
// already track the design import closely); only the family per role moved,
// toward the import's heavier headline weight.
export const type: Record<
  "display" | "bigNumber" | "title" | "heading" | "cardTitle" | "bodyStrong" | "body" | "label" | "meta" | "caption" | "tabLabel",
  TextStyle
> = {
  display: { fontFamily: fontFamily.bold, fontSize: 32, lineHeight: 36, letterSpacing: -0.02 * 32 },
  bigNumber: { fontFamily: fontFamily.bold, fontSize: 27, lineHeight: 31, letterSpacing: -0.02 * 27 },
  title: { fontFamily: fontFamily.bold, fontSize: 23, lineHeight: 26, letterSpacing: -0.015 * 23 },
  heading: { fontFamily: fontFamily.bold, fontSize: 17, lineHeight: 22 },
  cardTitle: { fontFamily: fontFamily.bold, fontSize: 15, lineHeight: 20 },
  bodyStrong: { fontFamily: fontFamily.medium, fontSize: 14, lineHeight: 20 },
  body: { fontFamily: fontFamily.regular, fontSize: 14, lineHeight: 20 },
  label: { fontFamily: fontFamily.regular, fontSize: 13, lineHeight: 18 },
  meta: { fontFamily: fontFamily.regular, fontSize: 12, lineHeight: 16 },
  caption: { fontFamily: fontFamily.regular, fontSize: 11, lineHeight: 14 },
  tabLabel: { fontFamily: fontFamily.semiBold, fontSize: 10.5, lineHeight: 13 },
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
// floor, Machado 2009 CVD deltaE, WCAG contrast) against all three dark
// ground presets, not chosen by eye. See plan doc for the validator runs.
// Left un-reversed and un-revalidated for the light ground added in v3 —
// these are opaque fill swatches (bars, heatmap cells), not text needing
// ground-contrast, so a pale-to-saturated ramp reads fine on either ground;
// flagged here so a real contrast pass against the light ground is a known
// follow-up rather than a silent gap.
//
// A 3+-slot categorical set is not achievable on Nocturne: the accent is
// blue-violet, so every cyan/teal candidate collapses against it under
// deuteranopia. Sequential (one hue, the accent ramp) is the workhorse;
// categorical is capped at 2 slots.
// Curated, contrast-validated (WCAG >= 4.5:1 on all 3 dark ground presets)
// accent choices for the Settings screen. Deliberately excludes amber-ish
// hues: the chart system's fixed categorical secondary is
// chart.categoricalSecondary (#bd8a35) below, and an amber accent would
// make the accent-vs-deductions pair in every budget chart indistinguishable.
// Light-mode variants (used when Settings' mode toggle is "light") are
// mechanically darkened via `darken()` in ThemeProvider, not independently
// validated the way the dark hexes below are.
export const accentOptions = [
  { name: "Blurple", hex: "#8b8bf0" },
  { name: "Rose", hex: "#d97a9c" },
  { name: "Teal", hex: "#4fb7ab" },
  { name: "Sky", hex: "#6fa8dc" },
  { name: "Green", hex: "#7ab876" },
] as const;

// RGB-scale factor for deriving a light-mode accent from a dark-native hex —
// matches the ratio between the design import's own light (#5b5bd6) and
// dark (#8b8bf0) default accent.
export const LIGHT_ACCENT_DARKEN_FACTOR = 0.65;

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

// Colorful icon-tile tint pairs (bg + fg) from the design import's
// t1bg/t1fg .. t5bg/t5fg — used for Quick Access / "My Day" style icon
// tiles where the app wants a distinct hue per feature rather than the
// single-accent monochrome tiles v2 used everywhere.
export const tileDark = [
  { bg: "#1e2a3d", fg: "#7fb3ef" },
  { bg: "#282142", fg: "#a893fa" },
  { bg: "#182f2b", fg: "#5cc7b0" },
  { bg: "#331f19", fg: "#f0906b" },
  { bg: "#332a13", fg: "#e6bc5c" },
] as const;

export const tileLight = [
  { bg: "#e8f0fe", fg: "#4a90e2" },
  { bg: "#efe9fe", fg: "#7c5cf0" },
  { bg: "#e6f7f2", fg: "#2f9e8a" },
  { bg: "#fdece7", fg: "#e8734a" },
  { bg: "#fdf3d7", fg: "#c9922c" },
] as const;
