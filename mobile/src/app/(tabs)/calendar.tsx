import { CalendarBlank, Plus } from "phosphor-react-native";
import { useCallback, useMemo, useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { createEvent, deleteEvent, listEvents } from "@/api/events";
import type { CalendarEvent } from "@/api/types";
import { Card } from "@/components/Card";
import { ComposeSheet } from "@/components/ComposeSheet";
import { FAB } from "@/components/FAB";
import { Heatmap, type HeatmapCell } from "@/components/charts";
import { ListScreen } from "@/components/ListScreen";
import { Skeleton } from "@/components/Skeleton";
import { SwipeableRow } from "@/components/SwipeableRow";
import { Tag } from "@/components/Tag";
import { useResource } from "@/hooks/useResource";
import { AnimatedListItem, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatDayHeader, formatEventTime } from "@/utils/date";

const DAY_RANGES = [7, 14, 30];

function eventDate(event: CalendarEvent): Date {
  if (!event.start) return new Date();
  if (event.allDay) {
    const [y, m, d] = event.start.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(event.start);
}

function groupByDay(events: CalendarEvent[]): { key: string; date: Date; events: CalendarEvent[] }[] {
  const groups: { key: string; date: Date; events: CalendarEvent[] }[] = [];
  for (const event of events) {
    const date = eventDate(event);
    const key = date.toDateString();
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.events.push(event);
    } else {
      groups.push({ key, date, events: [event] });
    }
  }
  return groups;
}

function densityStrip(events: CalendarEvent[], days: number): HeatmapCell[] {
  const counts = new Map<string, number>();
  for (const event of events) {
    const key = eventDate(event).toDateString();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const today = new Date();
  const cells: HeatmapCell[] = [];
  for (let i = 0; i < days; i += 1) {
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() + i);
    const count = counts.get(date.toDateString()) ?? 0;
    // weekday: Monday=0..Sunday=6 (JS getDay() is Sunday=0..Saturday=6)
    const weekday = (date.getDay() + 6) % 7;
    cells.push({ date: date.toISOString().slice(0, 10), label: String(date.getDate()), weekday, value: count, count });
  }
  return cells;
}

export default function CalendarScreen() {
  const theme = useTheme();
  const [days, setDays] = useState(7);
  const [composeVisible, setComposeVisible] = useState(false);

  const fetcher = useCallback(() => listEvents(days), [days]);
  const { data, loading, error, refetch } = useResource<CalendarEvent[]>(fetcher, "Couldn't load your calendar.");

  const handleDelete = (id: string) => {
    deleteEvent(id).finally(refetch);
  };

  const handleCreate = async (message: string) => {
    await createEvent(message);
    refetch();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <HStack gap={2} p={4} pb={2}>
        {DAY_RANGES.map((range) => (
          <PressableScale key={range} onPress={() => setDays(range)} accessibilityRole="button" accessibilityLabel={`Show ${range} days`}>
            <Stack py={1.5} px={4} radius="pill" bg={days === range ? theme.colors.accent : theme.colors.surface}>
              <Text variant="meta" style={{ color: days === range ? theme.colors.bg : theme.colors.neutral[400], fontFamily: theme.fontFamily.medium }}>
                {range} days
              </Text>
            </Stack>
          </PressableScale>
        ))}
      </HStack>

      <ListScreen
        data={data}
        loading={loading}
        error={error}
        refetch={refetch}
        skeleton={
          <Stack p={4} gap={3}>
            <Skeleton height={80} radius={theme.radius.md} />
            <Skeleton height={80} radius={theme.radius.md} />
            <Skeleton height={80} radius={theme.radius.md} />
          </Stack>
        }
        isEmpty={(events) => events.length === 0}
        emptyMessage="No events in this range."
        emptyIcon={CalendarBlank}
      >
        {(events) => (
          <CalendarBody events={events} days={days} onDelete={handleDelete} />
        )}
      </ListScreen>

      <FAB IconComponent={Plus} accessibilityLabel="Add event" onPress={() => setComposeVisible(true)} />
      <ComposeSheet
        visible={composeVisible}
        onClose={() => setComposeVisible(false)}
        onSubmit={handleCreate}
        title="New event"
        placeholder="e.g. lunch with Sam tomorrow 1pm"
      />
    </SafeAreaView>
  );
}

function CalendarBody({ events, days, onDelete }: { events: CalendarEvent[]; days: number; onDelete: (id: string) => void }) {
  const theme = useTheme();
  const groups = useMemo(() => groupByDay(events), [events]);
  const density = useMemo(() => densityStrip(events, days), [events, days]);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[1], paddingBottom: theme.spacing[10], gap: theme.spacing[4] }}>
      <Card>
        <Stack gap={3}>
          <Text variant="label" tone="secondary">
            Density
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Heatmap cells={density} />
          </ScrollView>
        </Stack>
      </Card>

      {groups.map((group, groupIndex) => (
        <AnimatedListItem key={group.key} index={groupIndex}>
          <Stack gap={2}>
            <Text variant="label" tone="secondary">
              {formatDayHeader(group.date)}
            </Text>
            <Card padding={0}>
              {group.events.map((event, index) => (
                <SwipeableRow key={event.id} onDelete={() => onDelete(event.id)}>
                  <HStack
                    align="center"
                    gap={3}
                    py={3}
                    px={4}
                    style={{ borderTopWidth: index === 0 ? 0 : 1, borderTopColor: theme.colors.divider }}
                  >
                    {event.allDay ? (
                      <Tag label="All day" variant="accent" />
                    ) : (
                      <Text variant="label" tone="secondary" numeric style={{ width: 52, fontFamily: theme.fontFamily.medium }}>
                        {formatEventTime(event.start, false)}
                      </Text>
                    )}
                    <Text variant="body" style={{ flex: 1 }}>
                      {event.title}
                    </Text>
                  </HStack>
                </SwipeableRow>
              ))}
            </Card>
          </Stack>
        </AnimatedListItem>
      ))}
    </ScrollView>
  );
}
