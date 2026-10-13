import { Plus } from "phosphor-react-native";
import { useCallback, useMemo, useState } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { createEvent, deleteEvent, listEventsRange } from "@/api/events";
import type { CalendarEvent } from "@/api/types";
import { DayAgenda, indexEventsByDay, MonthGrid } from "@/components/calendar";
import { Card } from "@/components/Card";
import { ComposeSheet } from "@/components/ComposeSheet";
import { ErrorState } from "@/components/ErrorState";
import { FAB } from "@/components/FAB";
import { Skeleton } from "@/components/Skeleton";
import { useResource } from "@/hooks/useResource";
import { HStack, Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { addMonths, monthMatrix, wibDate, wibDayKey, wibParts } from "@/utils/date";

type MonthEvents = { key: string; events: CalendarEvent[] };

function currentMonth() {
  const { year, month } = wibParts(new Date());
  return { year, month };
}

export default function CalendarScreen() {
  const theme = useTheme();
  const [visible, setVisible] = useState(currentMonth);
  const [selected, setSelected] = useState(() => new Date());
  const [composeVisible, setComposeVisible] = useState(false);

  // Fetch the whole 6-week grid, so leading/trailing days get their dots too.
  const weeks = useMemo(() => monthMatrix(visible.year, visible.month), [visible]);
  const rangeStart = wibDayKey(weeks[0][0]);
  const rangeEnd = wibDayKey(weeks[5][6]);
  const monthKey = `${rangeStart}_${rangeEnd}`;

  const fetcher = useCallback(
    () => listEventsRange(rangeStart, rangeEnd).then((events): MonthEvents => ({ key: `${rangeStart}_${rangeEnd}`, events })),
    [rangeStart, rangeEnd],
  );
  const { data, loading, error, refetch, mutate } = useResource<MonthEvents>(fetcher, "Couldn't load your calendar.");

  // The previous month's data stays on screen (dimmed) until the new month arrives.
  const stale = data !== null && data.key !== monthKey;
  const eventsByDay = useMemo(() => (stale || !data ? new Map<string, CalendarEvent[]>() : indexEventsByDay(data.events)), [data, stale]);
  const dayEvents = eventsByDay.get(wibDayKey(selected)) ?? [];

  const changeMonth = (delta: number) => {
    const next = addMonths(visible.year, visible.month, delta);
    setVisible(next);
    const today = wibParts(new Date());
    setSelected(today.year === next.year && today.month === next.month ? new Date() : wibDate(next.year, next.month, 1));
  };

  const selectDay = (date: Date) => {
    const { year, month } = wibParts(date);
    // Tapping a leading/trailing day from a neighbouring month moves to that month.
    if (year !== visible.year || month !== visible.month) setVisible({ year, month });
    setSelected(date);
  };

  const goToday = () => {
    setVisible(currentMonth());
    setSelected(new Date());
  };

  const handleDelete = (id: string) => {
    const removed = data?.events.find((event) => event.id === id);
    if (!removed) return;
    mutate(
      (prev) => ({ ...prev, events: prev.events.filter((event) => event.id !== id) }),
      (prev) => ({ ...prev, events: [...prev.events, removed] }),
      () => deleteEvent(id),
    );
  };

  const handleCreate = async (message: string) => {
    await createEvent(message);
    refetch();
  };

  if (error && data === null) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
        <ErrorState message={error} onRetry={refetch} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: theme.spacing[4], paddingBottom: theme.spacing[12] * 2, gap: theme.spacing[5] }}
      >
        <Card>
          {loading && data === null ? (
            <CalendarSkeleton />
          ) : (
            <MonthGrid
              year={visible.year}
              month={visible.month}
              selected={selected}
              eventsByDay={eventsByDay}
              stale={stale}
              onSelect={selectDay}
              onChangeMonth={changeMonth}
              onToday={goToday}
            />
          )}
        </Card>

        {data !== null && !stale ? <DayAgenda date={selected} events={dayEvents} onDelete={handleDelete} /> : null}
      </ScrollView>

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

function CalendarSkeleton() {
  const theme = useTheme();
  return (
    <Stack gap={3}>
      <HStack justify="space-between" align="center">
        <Skeleton height={26} width={160} radius={theme.radius.sm} />
        <Skeleton height={26} width={64} radius={theme.radius.sm} />
      </HStack>
      {Array.from({ length: 6 }, (_, row) => (
        <HStack key={row} justify="space-around">
          {Array.from({ length: 7 }, (_, col) => (
            <Skeleton key={col} height={34} width={34} radius={17} />
          ))}
        </HStack>
      ))}
    </Stack>
  );
}
