import { useRouter } from "expo-router";
import { CaretRight, Check, Wallet } from "phosphor-react-native";
import { useEffect, useState } from "react";
import { ScrollView, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { DEFAULT_API_URL, getApiUrl, setApiUrlOverride } from "@/api/client";
import { Card } from "@/components/Card";
import { ScreenHeader } from "@/components/ScreenHeader";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useSettings } from "@/theme/SettingsProvider";
import { useTheme } from "@/theme/ThemeProvider";
import { accentOptions, cornerPresets, groundPresets, type CornerPresetName, type GroundPresetName } from "@/theme/tokens";

const GROUND_OPTIONS: GroundPresetName[] = ["Midnight", "Deep indigo", "Slate"];
const CORNER_OPTIONS: CornerPresetName[] = ["Rounded", "Crisp"];

export default function SettingsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { themeConfig, setThemeConfig, userName, setUserName } = useSettings();
  const [nameDraft, setNameDraft] = useState(userName);

  // Lets one installed build point at the deployed backend or your laptop,
  // switchable without a rebuild — see api/client.ts's getApiUrl/
  // setApiUrlOverride. Falls back to the build-time EXPO_PUBLIC_API_URL
  // until the stored override (if any) finishes loading.
  const [apiUrlDraft, setApiUrlDraft] = useState(DEFAULT_API_URL);
  useEffect(() => {
    getApiUrl().then(setApiUrlDraft);
  }, []);

  const applyApiUrl = () => {
    const trimmed = apiUrlDraft.trim();
    setApiUrlOverride(trimmed === DEFAULT_API_URL ? null : trimmed);
  };

  const resetApiUrl = () => {
    setApiUrlOverride(null);
    setApiUrlDraft(DEFAULT_API_URL);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Settings" />
      <ScrollView contentContainerStyle={{ padding: theme.spacing[4], gap: theme.spacing[4] }}>
        <Card>
          <Stack gap={2}>
            <Text variant="label" tone="secondary">
              Your name
            </Text>
            <TextInput
              value={nameDraft}
              onChangeText={setNameDraft}
              onBlur={() => setUserName(nameDraft)}
              onSubmitEditing={() => setUserName(nameDraft)}
              placeholder="Devan"
              placeholderTextColor={theme.colors.neutral[500]}
              style={{ ...theme.type.body, color: theme.colors.text }}
              returnKeyType="done"
            />
          </Stack>
        </Card>

        <Card>
          <Stack gap={3}>
            <Text variant="label" tone="secondary">
              Accent
            </Text>
            <HStack gap={3} wrap>
              {accentOptions.map((option) => {
                const selected = themeConfig.accent === option.hex;
                return (
                  <PressableScale
                    key={option.hex}
                    onPress={() => setThemeConfig({ ...themeConfig, accent: option.hex })}
                    accessibilityRole="button"
                    accessibilityLabel={`Accent ${option.name}`}
                  >
                    <View
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: theme.radius.full,
                        backgroundColor: option.hex,
                        alignItems: "center",
                        justifyContent: "center",
                        borderWidth: selected ? 2 : 0,
                        borderColor: theme.colors.text,
                      }}
                    >
                      {selected ? <Check size={16} weight="bold" color={theme.colors.bg} /> : null}
                    </View>
                  </PressableScale>
                );
              })}
            </HStack>
          </Stack>
        </Card>

        <Card>
          <Stack gap={3}>
            <Text variant="label" tone="secondary">
              Ground
            </Text>
            <HStack gap={3}>
              {GROUND_OPTIONS.map((name) => {
                const preset = groundPresets[name];
                const selected = themeConfig.groundPreset === name;
                return (
                  <PressableScale
                    key={name}
                    onPress={() => setThemeConfig({ ...themeConfig, groundPreset: name })}
                    accessibilityRole="button"
                    accessibilityLabel={`Ground ${name}`}
                    style={{ flex: 1 }}
                  >
                    <Stack gap={1.5} align="center">
                      <View
                        style={{
                          width: "100%",
                          height: 40,
                          borderRadius: theme.radius.md,
                          backgroundColor: preset.bg,
                          borderWidth: selected ? 2 : 1,
                          borderColor: selected ? theme.colors.accent : theme.colors.divider,
                          overflow: "hidden",
                        }}
                      >
                        <View style={{ position: "absolute", right: 0, bottom: 0, top: "50%", left: "50%", backgroundColor: preset.surface }} />
                      </View>
                      <Text variant="caption" tone={selected ? "accent" : "muted"}>
                        {name}
                      </Text>
                    </Stack>
                  </PressableScale>
                );
              })}
            </HStack>
          </Stack>
        </Card>

        <Card>
          <Stack gap={3}>
            <Text variant="label" tone="secondary">
              Corners
            </Text>
            <HStack gap={3}>
              {CORNER_OPTIONS.map((name) => {
                const preset = cornerPresets[name];
                const selected = themeConfig.cornerPreset === name;
                return (
                  <PressableScale
                    key={name}
                    onPress={() => setThemeConfig({ ...themeConfig, cornerPreset: name })}
                    accessibilityRole="button"
                    accessibilityLabel={`Corners ${name}`}
                    style={{ flex: 1 }}
                  >
                    <Stack gap={1.5} align="center">
                      <View
                        style={{
                          width: "100%",
                          height: 40,
                          borderRadius: preset.lg,
                          backgroundColor: theme.colors.bg,
                          borderWidth: selected ? 2 : 1,
                          borderColor: selected ? theme.colors.accent : theme.colors.divider,
                        }}
                      />
                      <Text variant="caption" tone={selected ? "accent" : "muted"}>
                        {name}
                      </Text>
                    </Stack>
                  </PressableScale>
                );
              })}
            </HStack>
          </Stack>
        </Card>

        <Card>
          <Stack gap={2}>
            <Text variant="label" tone="secondary">
              API Server
            </Text>
            <TextInput
              value={apiUrlDraft}
              onChangeText={setApiUrlDraft}
              onBlur={applyApiUrl}
              onSubmitEditing={applyApiUrl}
              placeholder={DEFAULT_API_URL || "http://192.168.1.23:5000"}
              placeholderTextColor={theme.colors.neutral[500]}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={{ ...theme.type.body, color: theme.colors.text }}
              returnKeyType="done"
            />
            <PressableScale onPress={resetApiUrl} accessibilityRole="button" accessibilityLabel="Reset API server to default">
              <Text variant="caption" tone="accent">
                Reset to bundled default
              </Text>
            </PressableScale>
          </Stack>
        </Card>

        <PressableScale onPress={() => router.push("/budget")} accessibilityRole="button" accessibilityLabel="Budget">
          <Card>
            <HStack align="center" gap={3}>
              <Wallet size={18} color={theme.colors.accent} />
              <Text variant="body" style={{ flex: 1 }}>
                Budget
              </Text>
              <CaretRight size={16} color={theme.colors.neutral[500]} />
            </HStack>
          </Card>
        </PressableScale>
      </ScrollView>
    </SafeAreaView>
  );
}
