import type { Icon } from "phosphor-react-native";
import { Microphone, Paperclip, PaperPlaneRight } from "phosphor-react-native";
import { ScrollView, TextInput } from "react-native";

import { QuickChip } from "./QuickChip";
import { GlassSurface } from "@/components/GlassSurface";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ComposerProps = {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  quickChips: { label: string; message: string; IconComponent?: Icon }[];
  onQuickChip: (message: string) => void;
};

export function Composer({ value, onChangeText, onSend, quickChips, onQuickChip }: ComposerProps) {
  const theme = useTheme();
  const canSend = value.trim().length > 0;

  return (
    <GlassSurface style={{ borderTopWidth: 1, borderTopColor: theme.colors.divider }}>
      <Stack py={3} gap={3}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: theme.spacing[4], gap: theme.spacing[2] }}>
          {quickChips.map((chip) => (
            <QuickChip key={chip.label} label={chip.label} IconComponent={chip.IconComponent} onPress={() => onQuickChip(chip.message)} />
          ))}
        </ScrollView>

        <HStack align="center" gap={3} px={4}>
          <HStack
            flex={1}
            align="center"
            gap={2}
            py={2}
            px={4}
            radius="pill"
            bg={theme.colors.bg}
            style={{ borderWidth: 1, borderColor: theme.colors.divider }}
          >
            <TextInput
              value={value}
              onChangeText={onChangeText}
              placeholder="Type a message…"
              placeholderTextColor={theme.colors.neutral[500]}
              style={{ flex: 1, ...theme.type.body, color: theme.colors.text, padding: theme.spacing[0] }}
              multiline
              accessibilityLabel="Message input"
            />
            <PressableScale accessibilityRole="button" accessibilityLabel="Attach a file" hitSlop={8}>
              <Paperclip size={18} color={theme.colors.neutral[400]} />
            </PressableScale>
            <PressableScale accessibilityRole="button" accessibilityLabel="Record a voice message" hitSlop={8}>
              <Microphone size={18} color={theme.colors.neutral[400]} />
            </PressableScale>
          </HStack>

          <PressableScale
            onPress={onSend}
            disabled={!canSend}
            accessibilityRole="button"
            accessibilityLabel="Send message"
            style={{
              width: 42,
              height: 42,
              borderRadius: theme.radius.full,
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: theme.colors.accent,
              opacity: canSend ? 1 : 0.5,
            }}
          >
            <PaperPlaneRight size={18} weight="fill" color={theme.colors.bg} />
          </PressableScale>
        </HStack>
      </Stack>
    </GlassSurface>
  );
}
