import { useCallback, useState } from "react";

import { resetChat, sendChatMessage } from "@/api/chat";
import { ApiError } from "@/api/client";
import type { ChatMessage } from "@/api/types";

let nextId = 0;
function makeId() {
  nextId += 1;
  return `msg-${Date.now()}-${nextId}`;
}

export type UseChatResult = {
  messages: ChatMessage[];
  draft: string;
  setDraft: (text: string) => void;
  isAssistantTyping: boolean;
  sendMessage: (text?: string) => Promise<void>;
  newChat: () => Promise<void>;
};

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);

  const sendMessage = useCallback(
    async (text?: string) => {
      const content = (text ?? draft).trim();
      if (!content) return;

      setMessages((prev) => [...prev, { id: makeId(), role: "user", text: content }]);
      setDraft("");
      setIsAssistantTyping(true);

      try {
        const result = await sendChatMessage(content);
        setMessages((prev) => [
          ...prev,
          { id: makeId(), role: "assistant", kind: result.kind, text: result.text, data: result.data },
        ]);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong. Try again.";
        setMessages((prev) => [...prev, { id: makeId(), role: "assistant", kind: "text", text: message, data: null }]);
      } finally {
        setIsAssistantTyping(false);
      }
    },
    [draft],
  );

  const newChat = useCallback(async () => {
    setMessages([]);
    setDraft("");
    try {
      await resetChat();
    } catch {
      // conversation history is server-side only; a failed reset here just
      // means the next reply may see stale context, not worth surfacing.
    }
  }, []);

  return { messages, draft, setDraft, isAssistantTyping, sendMessage, newChat };
}
