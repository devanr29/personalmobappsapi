import { Note, Plus } from "phosphor-react-native";
import { useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { createNote, deleteNote, listNotes } from "@/api/notes";
import type { NoteOrIdea } from "@/api/types";
import { ComposeSheet } from "@/components/ComposeSheet";
import { FAB } from "@/components/FAB";
import { ListScreen } from "@/components/ListScreen";
import { NoteListCard } from "@/components/NoteListCard";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { SwipeableRow } from "@/components/SwipeableRow";
import { useResource } from "@/hooks/useResource";
import { AnimatedListItem } from "@/theme/motion";
import { Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function NotesScreen() {
  const theme = useTheme();
  const [composeVisible, setComposeVisible] = useState(false);
  const { data, loading, error, refetch } = useResource<NoteOrIdea[]>(listNotes, "Couldn't load your notes.");

  const handleDelete = (index: number) => {
    deleteNote(index).finally(refetch);
  };

  const handleCreate = async (message: string) => {
    await createNote(message);
    refetch();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Notes" />
      <ListScreen
        data={data}
        loading={loading}
        error={error}
        refetch={refetch}
        skeleton={
          <Stack p={4} gap={3}>
            <Skeleton height={56} radius={theme.radius.md} />
            <Skeleton height={56} radius={theme.radius.md} />
            <Skeleton height={56} radius={theme.radius.md} />
          </Stack>
        }
        isEmpty={(notes) => notes.length === 0}
        emptyMessage="No notes yet. Tap + to add one."
        emptyIcon={Note}
      >
        {(notes) => (
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: theme.spacing[4], paddingBottom: theme.spacing[10], gap: theme.spacing[3] }}>
            {notes.map((note, i) => (
              <AnimatedListItem key={note.index} index={i}>
                <SwipeableRow onDelete={() => handleDelete(note.index)}>
                  <NoteListCard item={note} />
                </SwipeableRow>
              </AnimatedListItem>
            ))}
          </ScrollView>
        )}
      </ListScreen>
      <FAB IconComponent={Plus} accessibilityLabel="Add note" onPress={() => setComposeVisible(true)} />
      <ComposeSheet
        visible={composeVisible}
        onClose={() => setComposeVisible(false)}
        onSubmit={handleCreate}
        title="New note"
        placeholder="What do you want to remember?"
      />
    </SafeAreaView>
  );
}
