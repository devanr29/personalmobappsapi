import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { BudgetProvider } from '@/features/budget/BudgetProvider';
import { registerForPushNotifications } from '@/notifications/registerPush';
import { SettingsProvider, useSettings } from '@/theme/SettingsProvider';
import { ThemeProvider as AppThemeProvider } from '@/theme/ThemeProvider';
import { useAppFonts } from '@/theme/fonts';

SplashScreen.preventAutoHideAsync();

// The native splash background (app.json) is the dark Nocturne ground, so
// there's no off-brand flash between the OS splash and this screen even
// though the resolved mode (light/dark) isn't known until settings load.
export default function RootLayout() {
  const [fontsLoaded] = useAppFonts();

  useEffect(() => {
    registerForPushNotifications();
  }, []);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SettingsProvider>
        <BudgetProvider>
          <ThemedApp />
        </BudgetProvider>
      </SettingsProvider>
    </GestureHandlerRootView>
  );
}

function ThemedApp() {
  const { themeConfig, loaded } = useSettings();

  useEffect(() => {
    if (loaded) {
      SplashScreen.hideAsync();
    }
  }, [loaded]);

  // Fonts are already guaranteed ready (RootLayout gates on them); wait for
  // persisted theme config too, so the mode/accent/ground/corner never
  // flashes default-then-saved on a cold start.
  if (!loaded) {
    return null;
  }

  return (
    <AppThemeProvider config={themeConfig}>
      <ThemeProvider value={themeConfig.mode === "dark" ? DarkTheme : DefaultTheme}>
        {/* Status bar icon color follows the in-app mode toggle, not the OS
            setting (userInterfaceStyle: "automatic" in app.json) — otherwise
            picking Light while the phone is in system dark mode renders
            white status-bar icons on a white background. */}
        <StatusBar style={themeConfig.mode === "dark" ? "light" : "dark"} />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(tabs)" />
        </Stack>
      </ThemeProvider>
    </AppThemeProvider>
  );
}
