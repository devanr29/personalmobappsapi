import { Quotes } from "phosphor-react-native";

import { Card } from "./Card";
import { Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type QuoteCardProps = {
  quote: string;
  author: string;
};

export function QuoteCard({ quote, author }: QuoteCardProps) {
  const theme = useTheme();

  return (
    <Card>
      <Stack gap={1.5}>
        <Quotes size={17} weight="fill" color={theme.colors.accent} />
        <Text variant="body" tone="secondary" style={{ fontStyle: "italic" }}>
          {quote}
        </Text>
        <Text variant="meta" tone="muted">
          — {author}
        </Text>
      </Stack>
    </Card>
  );
}
