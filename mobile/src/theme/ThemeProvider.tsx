import React, { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  chart,
  colors,
  cornerPresets,
  elevation,
  fontFamily,
  groundPresets,
  motion,
  neutral,
  accentRamp,
  numericType,
  radius,
  spacing,
  type,
  type CornerPresetName,
  type GroundPresetName,
} from "./tokens";

export interface ThemeConfig {
  accent: string;
  groundPreset: GroundPresetName;
  cornerPreset: CornerPresetName;
}

export type StatusLevel = "comfortable" | "manageable" | "tight" | "short";

export interface Theme {
  colors: typeof colors & {
    accent: string;
    bg: string;
    surface: string;
    neutral: typeof neutral;
    accentRamp: typeof accentRamp;
  };
  radius: typeof radius & ReturnType<() => (typeof cornerPresets)[CornerPresetName]>;
  spacing: typeof spacing;
  elevation: typeof elevation;
  type: typeof type;
  numericType: typeof numericType;
  fontFamily: typeof fontFamily;
  motion: typeof motion;
  status: Record<StatusLevel, string>;
  chart: typeof chart & { categorical: [string, string] };
  // Translucent surface used as the graceful fallback wherever glass
  // material (expo-glass-effect) isn't available.
  glassFallback: string;
}

const defaultConfig: ThemeConfig = {
  accent: colors.defaultAccent,
  groundPreset: "Midnight",
  cornerPreset: "Rounded",
};

function resolveTheme(config: ThemeConfig): Theme {
  const ground = groundPresets[config.groundPreset];
  const corner = cornerPresets[config.cornerPreset];
  return {
    colors: {
      ...colors,
      accent: config.accent,
      bg: ground.bg,
      surface: ground.surface,
      neutral,
      accentRamp,
    },
    radius: { ...radius, ...corner },
    spacing,
    elevation,
    type,
    numericType,
    fontFamily,
    motion,
    status: {
      comfortable: colors.positive,
      manageable: config.accent,
      tight: colors.tight,
      short: colors.negative,
    },
    chart: { ...chart, categorical: [config.accent, chart.categoricalSecondary] },
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
