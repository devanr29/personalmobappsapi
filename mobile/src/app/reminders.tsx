import { Alarm, Plus } from "phosphor-react-native";
import { useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { createReminder, deleteReminder, listReminders } from "@/api/reminders";
import type { Reminder } from "@/api/types";
import { Card } from "@/components/Card";
import { ComposeSheet } from "@/components/ComposeSheet";
import { FAB } from "@/components/FAB";
import { IconBadge } from "@/components/IconBadge";
import { ListScreen } from "@/components/ListScreen";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { SwipeableRow } from "@/components/SwipeableRow";
import { useResource } from "@/hooks/useResource";
import { AnimatedListItem } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatReminderTime } from "@/utils/date";

export default function RemindersScreen() {
  const theme = useTheme();
  const [composeVisible, setComposeVisible] = useState(false);
  const { data, loading, error, refetch } = useResource<Reminder[]>(listReminders, "Couldn't load your reminders.");

  const handleDelete = (id: number) => {
    deleteReminder(id).finally(refetch);
  };

  const handleCreate = async (message: string) => {
    await createReminder(message);
    refetch();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Reminders" />
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
        isEmpty={(reminders) => reminders.length === 0}
        emptyMessage="No upcoming reminders. Tap + to add one."
        emptyIcon={Alarm}
      >
        {(reminders) => (
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: theme.spacing[4], paddingBottom: theme.spacing[10], gap: theme.spacing[3] }}>
            {reminders.map((reminder, i) => (
              <AnimatedListItem key={reminder.id} index={i}>
                <SwipeableRow onDelete={() => handleDelete(reminder.id)}>
                  <Card>
                    <HStack align="center" gap={3}>
                      <IconBadge IconComponent={Alarm} tone="accent" size={32} />
                      <Stack flex={1}>
                        <Text variant="body">{reminder.content}</Text>
                        <Text variant="caption" tone="muted">
                          {formatReminderTime(reminder.remindAt)}
                        </Text>
                      </Stack>
                    </HStack>
                  </Card>
                </SwipeableRow>
              </AnimatedListItem>
            ))}
          </ScrollView>
        )}
      </ListScreen>
      <FAB IconComponent={Plus} accessibilityLabel="Add reminder" onPress={() => setComposeVisible(true)} />
      <ComposeSheet
        visible={composeVisible}
        onClose={() => setComposeVisible(false)}
        onSubmit={handleCreate}
        title="New reminder"
        placeholder="e.g. take medicine at 8am"
      />
    </SafeAreaView>
  );
}
