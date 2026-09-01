import { useRouter } from "expo-router";
import { Bell, Brain, CalendarCheck, CheckSquare, Lightbulb, Newspaper, Note } from "phosphor-react-native";
import { ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AskBar } from "@/components/AskBar";
import { BudgetCard } from "@/components/BudgetCard";
import { Card } from "@/components/Card";
import { Meter } from "@/components/charts";
import { HomeSkeleton } from "@/components/HomeSkeleton";
import { ListScreen } from "@/components/ListScreen";
import { QuoteCard } from "@/components/QuoteCard";
import { ReminderStrip } from "@/components/ReminderStrip";
import { ShortcutTile } from "@/components/ShortcutTile";
import { StatCard } from "@/components/StatCard";
import { TaskRow } from "@/components/TaskRow";
import { useHome } from "@/hooks/useHome";
import { AnimatedListItem, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useSettings } from "@/theme/SettingsProvider";
import { useTheme } from "@/theme/ThemeProvider";
import { formatEventTime, formatGreeting, formatLongDate, formatReminderTime } from "@/utils/date";

export default function HomeScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { data, loading, error, refetch, completeTaskOptimistic } = useHome();
  const { userName } = useSettings();

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ListScreen data={data} loading={loading} error={error} refetch={refetch} skeleton={<HomeSkeleton />}>
        {(data) => {
          const totalTaskCount = data.tasks.length;
          const activeTaskCount = data.tasks.filter((t) => t.status !== "completed").length;
          const completedRatio = totalTaskCount > 0 ? 1 - activeTaskCount / totalTaskCount : 0;
          const firstReminder = data.reminders[0] ?? null;

          return (
            <ScrollView
              style={{ flex: 1, backgroundColor: theme.colors.bg }}
              contentContainerStyle={{
                padding: theme.spacing[4],
                paddingTop: theme.spacing[5],
                paddingBottom: theme.spacing[3],
                gap: theme.spacing[4],
              }}
            >
              <HStack align="center" gap={3}>
                <Stack flex={1}>
                  <Text variant="label" tone="muted">
                    {formatGreeting(new Date())}
                  </Text>
                  <Text variant="title">{userName}</Text>
                  <Text variant="meta" tone="muted" style={{ marginTop: theme.spacing[0.5] }}>
                    {formatLongDate(new Date())}
                  </Text>
                </Stack>
                <PressableScale
                  onPress={() => router.push("/reminders")}
                  accessibilityRole="button"
                  accessibilityLabel="Reminders"
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: theme.radius.full,
                    backgroundColor: theme.colors.surface,
                    alignItems: "center",
                    justifyContent: "center",
                    ...theme.elevation.sm,
                  }}
                >
                  <Bell size={19} color={theme.colors.neutral[300]} />
                  {data.reminders.length > 0 ? (
                    <View
                      style={{
                        position: "absolute",
                        top: 8,
                        right: 9,
                        width: 6,
                        height: 6,
                        borderRadius: theme.radius.full,
                        backgroundColor: theme.colors.accent,
                      }}
                    />
                  ) : null}
                </PressableScale>
                <PressableScale
                  onPress={() => router.push("/settings")}
                  accessibilityRole="button"
                  accessibilityLabel="Settings"
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: theme.radius.full,
                    backgroundColor: theme.colors.accentRamp[800],
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Text variant="bodyStrong" style={{ color: theme.colors.accentRamp[100] }}>
                    {userName.charAt(0).toUpperCase()}
                  </Text>
                </PressableScale>
              </HStack>

              <AskBar onPress={() => router.push("/chat")} />

              <HStack align="center" justify="space-between">
                <Text variant="heading">Today</Text>
                <PressableScale onPress={() => router.push("/tasks")} accessibilityRole="button" accessibilityLabel="See all tasks">
                  <Text variant="meta" tone="accent">
                    See all
                  </Text>
                </PressableScale>
              </HStack>

              <HStack gap={3}>
                <StatCard
                  IconComponent={CheckSquare}
                  value={String(activeTaskCount)}
                  label="Active tasks"
                  tileIndex={1}
                  trend={totalTaskCount > 0 ? <Meter value={completedRatio} /> : undefined}
                />
                <StatCard
                  IconComponent={CalendarCheck}
                  value={data.nextEvent ? formatEventTime(data.nextEvent.start, data.nextEvent.allDay) : "—"}
                  valueVariant="heading"
                  valueTone="secondary"
                  label={data.nextEvent ? data.nextEvent.title : "No upcoming events"}
                  tileIndex={4}
                />
              </HStack>

              {data.tasks.length > 0 ? (
                <Card>
                  <Stack gap={3}>
                    {data.tasks.map((task, i) => (
                      <AnimatedListItem key={task.id} index={i}>
                        <TaskRow
                          title={task.title}
                          completed={task.status === "completed"}
                          onToggle={() => completeTaskOptimistic(task.id)}
                        />
                      </AnimatedListItem>
                    ))}
                  </Stack>
                </Card>
              ) : (
                <Card>
                  <Text variant="label" tone="muted">
                    No tasks today. Nice.
                  </Text>
                </Card>
              )}

              <BudgetCard data={data.budgetSummary} onSetup={() => router.push("/budget")} />

              {firstReminder ? (
                <ReminderStrip
                  title={firstReminder.content}
                  timeLabel={formatReminderTime(firstReminder.remindAt)}
                  onPress={() => router.push("/reminders")}
                />
              ) : null}

              <QuoteCard quote={data.quoteOfDay.quote} author={data.quoteOfDay.author} />

              <HStack gap={3}>
                <ShortcutTile IconComponent={Note} label="Notes" tileIndex={0} onPress={() => router.push("/notes")} />
                <ShortcutTile IconComponent={Lightbulb} label="Ideas" tileIndex={1} onPress={() => router.push("/ideas")} />
                <ShortcutTile IconComponent={Newspaper} label="News" tileIndex={2} onPress={() => router.push("/news")} />
                <ShortcutTile IconComponent={Brain} label="Brainstorm" tileIndex={3} onPress={() => router.push("/brainstorm")} />
              </HStack>
            </ScrollView>
          );
        }}
      </ListScreen>
    </SafeAreaView>
  );
}
