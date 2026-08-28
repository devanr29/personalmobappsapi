import type { NoteOrIdea } from "@/api/types";
import { Card } from "./Card";
import { Stack, Text } from "@/theme/primitives";

export function NoteListCard({ item }: { item: NoteOrIdea }) {
  return (
    <Card>
      <Stack gap={0.5}>
        <Text variant="body">{item.content}</Text>
        <Text variant="caption" tone="muted">
          {item.timestamp}
        </Text>
      </Stack>
    </Card>
  );
}
