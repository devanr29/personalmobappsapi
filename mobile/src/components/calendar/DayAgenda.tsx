import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { View } from "react-native";
import Animated, {
  FadeIn,
  FadeInDown,
  FadeOut,
  Keyframe,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
  ZoomIn,
} from "react-native-reanimated";

import type { CalendarEvent } from "@/api/types";
import { SwipeableRow } from "@/components/SwipeableRow";
import { Tag } from "@/components/Tag";
import { disclosure, easing } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { motion } from "@/theme/tokens";
import { formatClock, formatDayHeader, formatDuration, wibDate, wibDayKey, wibParts } from "@/utils/date";

import { eventEnd, eventStart } from "./events";

const TIME_COLUMN = 48;
const RAIL_COLUMN = 18;
const DOT_SIZE = 10;
const DOT_TOP = 14;

export type DayAgendaProps = {
  date: Date;
  events: CalendarEvent[];
  onDelete: (id: string) => void;
};

type Slot = { event: CalendarEvent; start: Date; end: Date };

/** Re-renders every minute so past/ongoing state and the now-line stay current. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

const stagger = (index: number) => Math.min(index, motion.staggerCap) * motion.staggerStep;

export function DayAgenda({ date, events, onDelete }: DayAgendaProps) {
  const theme = useTheme();
  const now = useNow();
  const dayKey = wibDayKey(date);
  const isToday = dayKey === wibDayKey(now);

  const { year, month, day } = wibParts(date);
  const dayStart = wibDate(year, month, day);
  const dayEnd = wibDate(year, month, day + 1);

  // Clamp multi-day timed events to this day; ones covering it entirely read as all-day.
  const allDay: CalendarEvent[] = [];
  const timed: Slot[] = [];
  for (const event of events) {
    const start = eventStart(event);
    const end = eventEnd(event);
    if (event.allDay || (start <= dayStart && end >= dayEnd)) {
      allDay.push(event);
    } else {
      timed.push({
        event,
        start: start < dayStart ? dayStart : start,
        end: end > dayEnd ? dayEnd : end,
      });
    }
  }

  const nowIndex = isToday && timed.length > 0 ? firstUpcoming(timed, now) : -1;
  const count = events.length;

  return (
    <Stack gap={3}>
      <HStack align="baseline" justify="space-between">
        <Animated.View key={dayKey} entering={FadeIn.duration(motion.duration.base)}>
          <Text variant="heading">{formatDayHeader(date)}</Text>
        </Animated.View>
        {count > 0 ? (
          <Text variant="meta" tone="muted" numeric>
            {count} {count === 1 ? "event" : "events"}
          </Text>
        ) : null}
      </HStack>

      {/* Keyed by day so switching days replays the staggered entrance. */}
      <Animated.View key={dayKey} layout={disclosure.layoutTransition} style={{ gap: theme.spacing[2] }}>
        {count === 0 ? (
          <Animated.View entering={FadeInDown.duration(motion.duration.slow).easing(easing.out)}>
            <Stack py={6} align="center" gap={1}>
              <Text variant="bodyStrong" tone="secondary">
                Nothing scheduled
              </Text>
              <Text variant="meta" tone="muted">
                Tap + to add something to this day.
              </Text>
            </Stack>
          </Animated.View>
        ) : null}

        {allDay.map((event, index) => (
          <Animated.View
            key={event.id}
            entering={FadeInDown.delay(stagger(index)).duration(motion.duration.slow).easing(easing.out)}
            exiting={disclosure.exiting}
            layout={disclosure.layoutTransition}
          >
            <SwipeableRow onDelete={() => onDelete(event.id)}>
              <EventCard title={event.title} accentBar>
                <Tag label="All day" variant="accent" />
              </EventCard>
            </SwipeableRow>
          </Animated.View>
        ))}

        {timed.map((slot, index) => {
          const position = allDay.length + index;
          const past = isToday ? slot.end <= now : dayEnd <= now;
          const ongoing = isToday && slot.start <= now && now < slot.end;
          return (
            <View key={slot.event.id}>
              {index === nowIndex ? <NowLine now={now} delay={stagger(position)} /> : null}
              <TimelineRow
                slot={slot}
                index={position}
                past={past}
                ongoing={ongoing}
                isLast={index === timed.length - 1}
                onDelete={() => onDelete(slot.event.id)}
              />
            </View>
          );
        })}
        {nowIndex === timed.length ? <NowLine now={now} delay={stagger(allDay.length + timed.length)} /> : null}
      </Animated.View>
    </Stack>
  );
}

/** Index of the first slot starting after `now` (timed.length if none). */
function firstUpcoming(timed: Slot[], now: Date): number {
  const index = timed.findIndex((slot) => slot.start > now);
  return index === -1 ? timed.length : index;
}

type TimelineRowProps = {
  slot: Slot;
  index: number;
  past: boolean;
  ongoing: boolean;
  isLast: boolean;
  onDelete: () => void;
};

function TimelineRow({ slot, index, past, ongoing, isLast, onDelete }: TimelineRowProps) {
  const theme = useTheme();
  const delay = stagger(index);
  const hasDuration = slot.end.getTime() > slot.start.getTime();
  const meta = hasDuration
    ? `${formatClock(slot.start)}–${formatClock(slot.end)} · ${formatDuration(slot.end.getTime() - slot.start.getTime())}`
    : formatClock(slot.start);

  // The rail segment below each dot grows downward after the row lands.
  const railGrow = new Keyframe({
    0: { transform: [{ scaleY: 0 }] },
    100: { transform: [{ scaleY: 1 }], easing: easing.out },
  })
    .delay(delay + motion.duration.fast)
    .duration(motion.duration.slow);

  return (
    <Animated.View
      entering={FadeInDown.delay(delay).duration(motion.duration.slow).easing(easing.out)}
      exiting={disclosure.exiting}
      layout={disclosure.layoutTransition}
      style={{ opacity: past ? 0.5 : 1 }}
    >
      <HStack align="stretch">
        <Stack style={{ width: TIME_COLUMN, paddingTop: theme.spacing[3] - 1 }}>
          <Text variant="label" numeric style={{ fontFamily: theme.fontFamily.medium, color: ongoing ? theme.colors.accent : theme.colors.text }}>
            {formatClock(slot.start)}
          </Text>
          {hasDuration ? (
            <Text variant="caption" tone="muted" numeric>
              {formatClock(slot.end)}
            </Text>
          ) : null}
        </Stack>

        <View style={{ width: RAIL_COLUMN, alignItems: "center" }}>
          {!isLast ? (
            <Animated.View
              entering={railGrow}
              style={{
                position: "absolute",
                top: DOT_TOP + DOT_SIZE,
                bottom: -theme.spacing[2] - DOT_TOP,
                width: 2,
                borderRadius: theme.radius.full,
                backgroundColor: theme.colors.neutral[800],
                transformOrigin: "top",
              }}
            />
          ) : null}
          <Animated.View entering={ZoomIn.delay(delay + motion.duration.fast).springify().damping(motion.spring.damping)} style={{ marginTop: DOT_TOP }}>
            {ongoing ? <PulseDot color={theme.colors.accent} /> : <RailDot color={past ? theme.colors.neutral[600] : theme.colors.accent} />}
          </Animated.View>
        </View>

        <View style={{ flex: 1, marginLeft: theme.spacing[2] }}>
          <SwipeableRow onDelete={onDelete}>
            <EventCard title={slot.event.title} accentBar={!past}>
              <HStack align="center" gap={2}>
                <Text variant="meta" tone="muted" numeric>
                  {meta}
                </Text>
                {ongoing ? <Tag label="Now" variant="accent" /> : null}
              </HStack>
            </EventCard>
          </SwipeableRow>
        </View>
      </HStack>
    </Animated.View>
  );
}

function EventCard({ title, accentBar, children }: { title: string; accentBar?: boolean; children: ReactNode }) {
  const theme = useTheme();
  return (
    <HStack radius="md" bg={theme.colors.surface} elevationLevel="sm" style={{ overflow: "hidden" }}>
      <View style={{ width: 3, backgroundColor: accentBar ? theme.colors.accent : theme.colors.neutral[800] }} />
      <Stack flex={1} gap={1} py={3} px={3}>
        <Text variant="bodyStrong" numberOfLines={2}>
          {title}
        </Text>
        {children}
      </Stack>
    </HStack>
  );
}

function RailDot({ color }: { color: string }) {
  const theme = useTheme();
  return (
    <View
      style={{
        width: DOT_SIZE,
        height: DOT_SIZE,
        borderRadius: DOT_SIZE / 2,
        backgroundColor: theme.colors.bg,
        borderWidth: 2,
        borderColor: color,
      }}
    />
  );
}

/** Solid dot with a soft expanding halo — marks what's happening now. */
function PulseDot({ color }: { color: string }) {
  const reduced = useReducedMotion();
  const pulse = useSharedValue(0);

  useEffect(() => {
    if (reduced) return;
    pulse.value = withRepeat(withTiming(1, { duration: 1600, easing: easing.out }), -1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced]);

  const halo = useAnimatedStyle(() => ({
    opacity: 0.5 * (1 - pulse.value),
    transform: [{ scale: 1 + pulse.value * 1.4 }],
  }));

  return (
    <View style={{ width: DOT_SIZE, height: DOT_SIZE, alignItems: "center", justifyContent: "center" }}>
      <Animated.View style={[{ position: "absolute", width: DOT_SIZE, height: DOT_SIZE, borderRadius: DOT_SIZE / 2, backgroundColor: color }, halo]} />
      <View style={{ width: DOT_SIZE, height: DOT_SIZE, borderRadius: DOT_SIZE / 2, backgroundColor: color }} />
    </View>
  );
}

function NowLine({ now, delay }: { now: Date; delay: number }) {
  const theme = useTheme();
  return (
    <Animated.View entering={FadeIn.delay(delay).duration(motion.duration.slow)} exiting={FadeOut} layout={disclosure.layoutTransition}>
      <HStack align="center" style={{ height: 20, marginBottom: theme.spacing[2] }} accessibilityLabel={`Now, ${formatClock(now)}`}>
        <Text variant="caption" tone="accent" numeric style={{ width: TIME_COLUMN, fontFamily: theme.fontFamily.semiBold }}>
          {formatClock(now)}
        </Text>
        <View style={{ width: RAIL_COLUMN, alignItems: "center" }}>
          <PulseDot color={theme.colors.accent} />
        </View>
        <View style={{ flex: 1, height: 1.5, borderRadius: theme.radius.full, backgroundColor: theme.colors.accent, marginLeft: theme.spacing[2] }} />
      </HStack>
    </Animated.View>
  );
}
