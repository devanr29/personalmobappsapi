import { CheckSquare } from "phosphor-react-native";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { completeTask, deleteTask, listTasks } from "@/api/tasks";
import type { Task } from "@/api/types";
import { Card } from "@/components/Card";
import { ListScreen } from "@/components/ListScreen";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { SwipeableRow } from "@/components/SwipeableRow";
import { TaskRow } from "@/components/TaskRow";
import { useResource } from "@/hooks/useResource";
import { AnimatedListItem } from "@/theme/motion";
import { Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function TasksScreen() {
  const theme = useTheme();
  const { data, loading, error, refetch, mutate } = useResource<Task[]>(listTasks, "Couldn't load your tasks.");

  const toggleComplete = (id: string) => {
    const setStatus = (status: Task["status"]) => (prev: Task[]) =>
      prev.map((t) => (t.id === id ? { ...t, status } : t));
    mutate(setStatus("completed"), setStatus("needsAction"), () => completeTask(id));
  };

  const handleDelete = (id: string) => {
    deleteTask(id).finally(refetch);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Tasks" />
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
        isEmpty={(tasks) => tasks.length === 0}
        emptyMessage="No tasks. Nice."
        emptyIcon={CheckSquare}
      >
        {(tasks) => (
          <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingBottom: theme.spacing[10], gap: theme.spacing[3] }}>
            {tasks.map((task, i) => (
              <AnimatedListItem key={task.id} index={i}>
                <SwipeableRow onDelete={() => handleDelete(task.id)}>
                  <Card>
                    <TaskRow title={task.title} completed={task.status === "completed"} onToggle={() => toggleComplete(task.id)} />
                  </Card>
                </SwipeableRow>
              </AnimatedListItem>
            ))}
          </ScrollView>
        )}
      </ListScreen>
    </SafeAreaView>
  );
}
