import { Lightbulb, Plus } from "phosphor-react-native";
import { useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { createIdea, deleteIdea, listIdeas } from "@/api/ideas";
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

export default function IdeasScreen() {
  const theme = useTheme();
  const [composeVisible, setComposeVisible] = useState(false);
  const { data, loading, error, refetch } = useResource<NoteOrIdea[]>(listIdeas, "Couldn't load your ideas.");

  const handleDelete = (index: number) => {
    deleteIdea(index).finally(refetch);
  };

  const handleCreate = async (message: string) => {
    await createIdea(message);
    refetch();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Ideas" />
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
        isEmpty={(ideas) => ideas.length === 0}
        emptyMessage="No ideas yet. Tap + to add one."
        emptyIcon={Lightbulb}
      >
        {(ideas) => (
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: theme.spacing[4], paddingBottom: theme.spacing[10], gap: theme.spacing[3] }}>
            {ideas.map((idea, i) => (
              <AnimatedListItem key={idea.index} index={i}>
                <SwipeableRow onDelete={() => handleDelete(idea.index)}>
                  <NoteListCard item={idea} />
                </SwipeableRow>
              </AnimatedListItem>
            ))}
          </ScrollView>
        )}
      </ListScreen>
      <FAB IconComponent={Plus} accessibilityLabel="Add idea" onPress={() => setComposeVisible(true)} />
      <ComposeSheet
        visible={composeVisible}
        onClose={() => setComposeVisible(false)}
        onSubmit={handleCreate}
        title="New idea"
        placeholder="What's the idea?"
      />
    </SafeAreaView>
  );
}
