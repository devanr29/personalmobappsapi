import { CheckCircle, Quotes } from "phosphor-react-native";
import { View } from "react-native";

import { AnimatedCurrency } from "@/components/AnimatedCurrency";
import { StackedBar } from "@/components/charts";
import type { ChatBudgetData, ChatMessage, ChatTaskData } from "@/api/types";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { parseQuote, stripMarkdown } from "@/utils/text";

const statusCopy: Record<ChatBudgetData["statusLevel"], string> = {
  short: "You're short this month",
  tight: "Tight — keep non-essentials minimal",
  manageable: "Manageable — watch your spending",
  comfortable: "Comfortable position",
};

function bubbleRadius(role: "user" | "assistant", lg: number, sm: number) {
  return role === "user"
    ? { borderTopLeftRadius: lg, borderTopRightRadius: lg, borderBottomRightRadius: sm, borderBottomLeftRadius: lg }
    : { borderTopLeftRadius: lg, borderTopRightRadius: lg, borderBottomRightRadius: lg, borderBottomLeftRadius: sm };
}

function TaskBubble({ text, data }: { text: string; data: ChatTaskData }) {
  const theme = useTheme();
  const synced = text.toLowerCase().includes("google tasks");
  return (
    <HStack gap={2} align="flex-start">
      <CheckCircle size={18} weight="fill" color={theme.colors.positive} />
      <Stack flex={1} gap={0.5}>
        <Text variant="bodyStrong" selectable>
          {data.content}
        </Text>
        <Text variant="meta" tone="muted">
          {synced ? "Also added to Google Tasks" : "Saved locally"}
        </Text>
      </Stack>
    </HStack>
  );
}

function QuoteBubble({ text }: { text: string }) {
  const theme = useTheme();
  const { quote, author } = parseQuote(text);
  return (
    <Stack gap={1.5}>
      <Quotes size={16} weight="fill" color={theme.colors.accent} />
      <Text variant="body" tone="secondary" style={{ fontStyle: "italic" }} selectable>
        {quote}
      </Text>
      <Text variant="meta" tone="muted">
        — {author}
      </Text>
    </Stack>
  );
}

function BudgetRow({ label, value, tone }: { label: string; value: string; tone?: "negative" }) {
  const theme = useTheme();
  return (
    <HStack justify="space-between">
      <Text variant="meta" tone="muted">
        {label}
      </Text>
      <Text variant="meta" tone={tone ?? "secondary"} numeric selectable style={{ fontFamily: theme.fontFamily.medium }}>
        {value}
      </Text>
    </HStack>
  );
}

function DeductionBreakdown({ items }: { items: ChatBudgetData["deductionBreakdown"] }) {
  if (items.length === 0) return null;
  return (
    <Stack gap={0.5} pl={3}>
      {items.map((item) => (
        <HStack key={item.name} justify="space-between">
          <Text variant="caption" tone="faint" selectable>
            {item.name}
          </Text>
          <Text variant="caption" tone="faint" numeric selectable>
            -{formatRupiah(item.amount)}
          </Text>
        </HStack>
      ))}
    </Stack>
  );
}

function BudgetBubble({ data }: { data: ChatBudgetData }) {
  const theme = useTheme();
  const [accent, amber] = theme.chart.categorical;
  const statusColor = theme.status[data.statusLevel];

  return (
    <Stack gap={3} style={{ minWidth: 220 }}>
      <Stack>
        <Text variant="bodyStrong">💰 Budget Breakdown</Text>
        <Text variant="caption" tone="muted" style={{ marginTop: theme.spacing[0.5] }}>
          {data.daysToPayday} days to payday
        </Text>
      </Stack>

      <StackedBar
        segments={[
          { value: Math.max(0, data.free), color: accent },
          { value: Math.max(0, data.deductions), color: amber },
        ]}
        total={data.remaining}
        thickness={6}
      />

      <Stack gap={1.5}>
        <BudgetRow label="Money in hand" value={formatRupiah(data.remaining)} />
        <Stack gap={1}>
          <BudgetRow label="Total deductions" value={`-${formatRupiah(data.deductions)}`} tone="negative" />
          <DeductionBreakdown items={data.deductionBreakdown} />
        </Stack>
        <BudgetRow label="Free money left" value={formatRupiah(data.free)} />
      </Stack>

      <HStack align="center" gap={2} py={2} px={3} radius="md" bg={theme.colors.accentRamp[900]}>
        <CheckCircle size={16} weight="fill" color={theme.colors.accentRamp[300]} />
        <Text variant="meta" style={{ flex: 1, color: theme.colors.accentRamp[200] }}>
          Daily budget <AnimatedCurrency value={data.dailyBudget} variant="meta" style={{ color: theme.colors.accentRamp[100] }} />
          /day
        </Text>
      </HStack>

      <HStack align="center" gap={1.5}>
        <View style={{ width: 8, height: 8, borderRadius: theme.radius.full, backgroundColor: statusColor }} />
        <Text variant="meta" tone="muted">
          {statusCopy[data.statusLevel]}
        </Text>
      </HStack>
    </Stack>
  );
}

function accessibilityLabelFor(message: ChatMessage): string {
  if (message.role === "user") return `You said: ${message.text}`;
  if (message.kind === "budget" && message.data) {
    const d = message.data as ChatBudgetData;
    return `Budget breakdown: daily budget ${formatRupiah(d.dailyBudget)} per day, ${statusCopy[d.statusLevel]}`;
  }
  if (message.kind === "task" && message.data) {
    return `Task added: ${(message.data as ChatTaskData).content}`;
  }
  if (message.kind === "quote") {
    const { quote, author } = parseQuote(message.text);
    return `Quote: ${quote}, by ${author}`;
  }
  return `Assistant: ${stripMarkdown(message.text)}`;
}

export function ChatBubble({ message }: { message: ChatMessage }) {
  const theme = useTheme();
  const isUser = message.role === "user";

  return (
    <Stack
      accessibilityLabel={accessibilityLabelFor(message)}
      py={2}
      px={3}
      bg={isUser ? theme.colors.accentRamp[800] : theme.colors.surface}
      style={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        maxWidth: "86%",
        ...bubbleRadius(message.role, theme.radius.lg, theme.radius.sm),
        ...(isUser ? {} : theme.elevation.sm),
      }}
    >
      {isUser ? (
        <Text variant="body" style={{ color: theme.colors.accentRamp[100] }} selectable>
          {message.text}
        </Text>
      ) : message.kind === "task" && message.data ? (
        <TaskBubble text={message.text} data={message.data as ChatTaskData} />
      ) : message.kind === "budget" && message.data ? (
        <BudgetBubble data={message.data as ChatBudgetData} />
      ) : message.kind === "quote" ? (
        <QuoteBubble text={message.text} />
      ) : (
        <Text variant="body" selectable>
          {stripMarkdown(message.text)}
        </Text>
      )}
    </Stack>
  );
}
