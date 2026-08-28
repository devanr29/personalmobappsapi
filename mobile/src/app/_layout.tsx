import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { BudgetProvider } from '@/features/budget/BudgetProvider';
import { registerForPushNotifications } from '@/notifications/registerPush';
import { SettingsProvider, useSettings } from '@/theme/SettingsProvider';
import { ThemeProvider as AppThemeProvider } from '@/theme/ThemeProvider';
import { useAppFonts } from '@/theme/fonts';

SplashScreen.preventAutoHideAsync();

// Nocturne is dark-only — no light-mode nav theme to switch to. The native
// splash background (app.json) is the Nocturne ground, so there is no
// off-brand flash between the OS splash and this screen.
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
      <ThemeProvider value={DarkTheme}>
        <SettingsProvider>
          <BudgetProvider>
            <ThemedApp />
          </BudgetProvider>
        </SettingsProvider>
      </ThemeProvider>
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
  // persisted theme config too, so the accent/ground/corner never flashes
  // default-then-saved on a cold start.
  if (!loaded) {
    return null;
  }

  return (
    <AppThemeProvider config={themeConfig}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
      </Stack>
    </AppThemeProvider>
  );
}
