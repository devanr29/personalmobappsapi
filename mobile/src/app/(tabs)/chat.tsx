import { Sparkle } from "phosphor-react-native";
import { useRef } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { GlassSurface } from "@/components/GlassSurface";
import { ChatBubble } from "@/components/chat/ChatBubble";
import { Composer } from "@/components/chat/Composer";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { useChat } from "@/hooks/useChat";
import { AnimatedListItem, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

const QUICK_CHIPS = [
  { label: "＋ Task", message: "add task " },
  { label: "⏰ Reminder", message: "remind me to " },
  { label: "💰 Budget", message: "budget" },
  { label: "📰 News", message: "news" },
];

export default function ChatScreen() {
  const theme = useTheme();
  const { messages, draft, setDraft, isAssistantTyping, sendMessage, newChat } = useChat();
  const scrollRef = useRef<ScrollView>(null);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
      >
        <GlassSurface style={{ borderBottomWidth: 1, borderBottomColor: theme.colors.divider }}>
          <HStack align="center" gap={3} py={3} px={4}>
            <View
              style={{
                width: 38,
                height: 38,
                borderRadius: theme.radius.full,
                backgroundColor: theme.colors.accentRamp[800],
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Sparkle size={17} weight="fill" color={theme.colors.accentRamp[200]} />
            </View>
            <Stack flex={1}>
              <Text variant="cardTitle">Assistant</Text>
              <HStack align="center" gap={1}>
                <View style={{ width: 6, height: 6, borderRadius: theme.radius.full, backgroundColor: theme.colors.positive }} />
                <Text variant="caption" tone="muted">
                  Online
                </Text>
              </HStack>
            </Stack>
            <PressableScale onPress={newChat} accessibilityRole="button" accessibilityLabel="Start a new chat" hitSlop={8}>
              <Text variant="meta" tone="accent" style={{ fontFamily: theme.fontFamily.medium }}>
                New Chat
              </Text>
            </PressableScale>
          </HStack>
        </GlassSurface>

        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[4], gap: theme.spacing[3], flexGrow: 1 }}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.length === 0 && !isAssistantTyping ? (
            <Stack flex={1} align="center" justify="center" gap={1.5} px={6}>
              <Sparkle size={22} weight="fill" color={theme.colors.accent} />
              <Text variant="body" tone="muted" align="center">
                Ask your assistant anything…
              </Text>
            </Stack>
          ) : (
            <>
              <Text variant="caption" tone="faint" align="center">
                Today
              </Text>
              {messages.map((message, i) => (
                <AnimatedListItem key={message.id} index={i}>
                  <ChatBubble message={message} />
                </AnimatedListItem>
              ))}
              {isAssistantTyping ? <TypingIndicator /> : null}
            </>
          )}
        </ScrollView>

        <Composer
          value={draft}
          onChangeText={setDraft}
          onSend={() => sendMessage()}
          quickChips={QUICK_CHIPS}
          onQuickChip={(message) => sendMessage(message)}
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
