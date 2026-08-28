// Persists the theme config (accent/ground/corner) and user profile that
// ThemeProvider's ThemeConfig always supported but nothing ever set —
// wired up here via AsyncStorage so Settings changes survive app restarts
// and propagate to every screen through the same context tree.
import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { colors } from "./tokens";
import type { ThemeConfig } from "./ThemeProvider";

const THEME_CONFIG_KEY = "nocturne.themeConfig";
const USER_NAME_KEY = "nocturne.userName";

const DEFAULT_THEME_CONFIG: ThemeConfig = {
  accent: colors.defaultAccent,
  groundPreset: "Midnight",
  cornerPreset: "Rounded",
};

const DEFAULT_USER_NAME = "Devan";

export interface SettingsContextValue {
  loaded: boolean;
  themeConfig: ThemeConfig;
  setThemeConfig: (config: ThemeConfig) => void;
  userName: string;
  setUserName: (name: string) => void;
}

const SettingsContext = createContext<SettingsContextValue>({
  loaded: false,
  themeConfig: DEFAULT_THEME_CONFIG,
  setThemeConfig: () => {},
  userName: DEFAULT_USER_NAME,
  setUserName: () => {},
});

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [loaded, setLoaded] = useState(false);
  const [themeConfig, setThemeConfigState] = useState<ThemeConfig>(DEFAULT_THEME_CONFIG);
  const [userName, setUserNameState] = useState(DEFAULT_USER_NAME);

  useEffect(() => {
    (async () => {
      try {
        const [storedConfig, storedName] = await Promise.all([
          AsyncStorage.getItem(THEME_CONFIG_KEY),
          AsyncStorage.getItem(USER_NAME_KEY),
        ]);
        if (storedConfig) setThemeConfigState(JSON.parse(storedConfig));
        if (storedName) setUserNameState(storedName);
      } catch {
        // Corrupt or unavailable storage — fall back to defaults silently;
        // Settings will overwrite it with a valid value on next change.
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

  const setThemeConfig = (config: ThemeConfig) => {
    setThemeConfigState(config);
    AsyncStorage.setItem(THEME_CONFIG_KEY, JSON.stringify(config)).catch(() => {});
  };

  const setUserName = (name: string) => {
    const trimmed = name.trim() || DEFAULT_USER_NAME;
    setUserNameState(trimmed);
    AsyncStorage.setItem(USER_NAME_KEY, trimmed).catch(() => {});
  };

  const value = useMemo(
    () => ({ loaded, themeConfig, setThemeConfig, userName, setUserName }),
    [loaded, themeConfig, userName],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  return useContext(SettingsContext);
}
