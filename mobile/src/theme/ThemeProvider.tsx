import React, { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  chart,
  cornerPresets,
  darken,
  darkColors,
  elevationDark,
  elevationLight,
  fontFamily,
  groundPresets,
  lightColors,
  lightGround,
  LIGHT_ACCENT_DARKEN_FACTOR,
  motion,
  neutral,
  accentRamp,
  numericType,
  radius,
  reverseRamp,
  spacing,
  tileDark,
  tileLight,
  type,
  type CornerPresetName,
  type ElevationLevel,
  type GroundPresetName,
  type NineStepRamp,
  type TileTint,
} from "./tokens";

export type ThemeMode = "light" | "dark";

export interface ThemeConfig {
  mode: ThemeMode;
  /** Always the dark-native hex — the light-mode variant is derived. */
  accent: string;
  groundPreset: GroundPresetName;
  cornerPreset: CornerPresetName;
}

export type StatusLevel = "comfortable" | "manageable" | "tight" | "short";

export interface Theme {
  mode: ThemeMode;
  colors: {
    text: string;
    divider: string;
    positive: string;
    negative: string;
    tight: string;
    defaultAccent: string;
    accent: string;
    bg: string;
    surface: string;
    neutral: NineStepRamp;
    accentRamp: NineStepRamp;
  };
  radius: typeof radius & ReturnType<() => (typeof cornerPresets)[CornerPresetName]>;
  spacing: typeof spacing;
  elevation: Record<"sm" | "md" | "lg", ElevationLevel>;
  type: typeof type;
  numericType: typeof numericType;
  fontFamily: typeof fontFamily;
  motion: typeof motion;
  status: Record<StatusLevel, string>;
  chart: {
    sequential: typeof chart.sequential;
    categoricalSecondary: string;
    track: string;
    axis: string;
    categorical: [string, string];
  };
  /** Colorful icon-tile tint pairs (bg + fg), 5 hues — see tokens.ts's tileDark/tileLight. */
  tile: readonly TileTint[];
  // Translucent surface used as the graceful fallback wherever glass
  // material (expo-glass-effect) isn't available.
  glassFallback: string;
}

const defaultConfig: ThemeConfig = {
  mode: "dark",
  accent: darkColors.defaultAccent,
  groundPreset: "Midnight",
  cornerPreset: "Rounded",
};

function resolveTheme(config: ThemeConfig): Theme {
  const isDark = config.mode === "dark";
  const palette = isDark ? darkColors : lightColors;
  const ground = isDark ? groundPresets[config.groundPreset] : lightGround;
  const corner = cornerPresets[config.cornerPreset];
  const resolvedNeutral = isDark ? neutral : reverseRamp(neutral);
  const resolvedAccentRamp = isDark ? accentRamp : reverseRamp(accentRamp);
  const accent = isDark ? config.accent : darken(config.accent, LIGHT_ACCENT_DARKEN_FACTOR);

  return {
    mode: config.mode,
    colors: {
      ...palette,
      accent,
      bg: ground.bg,
      surface: ground.surface,
      neutral: resolvedNeutral,
      accentRamp: resolvedAccentRamp,
    },
    radius: { ...radius, ...corner },
    spacing,
    elevation: isDark ? elevationDark : elevationLight,
    type,
    numericType,
    fontFamily,
    motion,
    status: {
      comfortable: palette.positive,
      manageable: accent,
      tight: palette.tight,
      short: palette.negative,
    },
    chart: { ...chart, track: resolvedNeutral[800], axis: resolvedNeutral[800], categorical: [accent, chart.categoricalSecondary] },
    tile: isDark ? tileDark : tileLight,
    glassFallback: `${ground.surface}eb`, // ~92% opacity
  };
}

const ThemeContext = createContext<Theme>(resolveTheme(defaultConfig));

export function ThemeProvider({
  config = defaultConfig,
  children,
}: {
  config?: ThemeConfig;
  children: ReactNode;
}) {
  const theme = useMemo(() => resolveTheme(config), [config]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}
