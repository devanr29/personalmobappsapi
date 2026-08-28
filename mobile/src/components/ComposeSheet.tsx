import { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, TextInput, View } from "react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ComposeSheetProps = {
  visible: boolean;
  onClose: () => void;
  onSubmit: (message: string) => Promise<void>;
  title: string;
  placeholder?: string;
};

export function ComposeSheet({ visible, onClose, onSubmit, title, placeholder = "Type a message…" }: ComposeSheetProps) {
  const theme = useTheme();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleClose = () => {
    if (submitting) return;
    setValue("");
    onClose();
  };

  const handleSubmit = async () => {
    const message = value.trim();
    if (!message || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(message);
      setValue("");
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={handleClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
            <Stack p={4} gap={3}>
              <Text variant="heading">{title}</Text>
              <TextInput
                value={value}
                onChangeText={setValue}
                placeholder={placeholder}
                placeholderTextColor={theme.colors.neutral[500]}
                style={{
                  ...theme.type.body,
                  color: theme.colors.text,
                  backgroundColor: theme.colors.bg,
                  borderWidth: 1,
                  borderColor: theme.colors.divider,
                  borderRadius: theme.radius.md,
                  padding: theme.spacing[3],
                  minHeight: 44,
                }}
                multiline
                autoFocus
                editable={!submitting}
                accessibilityLabel={title}
              />
              <HStack justify="flex-end" gap={3}>
                <Pressable onPress={handleClose} disabled={submitting} accessibilityRole="button" accessibilityLabel="Cancel">
                  <Box py={2} px={4}>
                    <Text variant="label" tone="muted">
                      Cancel
                    </Text>
                  </Box>
                </Pressable>
                <Pressable
                  onPress={handleSubmit}
                  disabled={submitting || value.trim().length === 0}
                  accessibilityRole="button"
                  accessibilityLabel="Submit"
                >
                  <HStack
                    align="center"
                    gap={1.5}
                    py={2}
                    px={4}
                    radius="pill"
                    bg={theme.colors.accent}
                    style={{ opacity: submitting || value.trim().length === 0 ? 0.5 : 1 }}
                  >
                    {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
                    <Text variant="label" style={{ color: theme.colors.bg }}>
                      Add
                    </Text>
                  </HStack>
                </Pressable>
              </HStack>
            </Stack>
          </GlassSurface>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}
