import * as Haptics from "expo-haptics";
import { CaretLeft, CaretRight } from "phosphor-react-native";
import { memo, useEffect, useMemo, useState } from "react";
import { Pressable, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  FadeIn,
  FadeOut,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withSpring,
  withTiming,
  type EntryExitAnimationFunction,
  type SharedValue,
} from "react-native-reanimated";

import type { CalendarEvent } from "@/api/types";
import { easing, PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { motion } from "@/theme/tokens";
import { formatMonthTitle, isSameWibDay, monthMatrix, wibDayKey, wibParts } from "@/utils/date";

const WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
const CELL_HEIGHT = 50;
const PILL_SIZE = 34;
const PILL_TOP = 4;
const MAX_DOTS = 3;
const SLIDE_DISTANCE = 56;
const SWIPE_DISTANCE = 50;
const SWIPE_VELOCITY = 500;

export type MonthGridProps = {
  year: number;
  month: number;
  selected: Date;
  eventsByDay: Map<string, CalendarEvent[]>;
  /** True while the visible month's events are still loading. */
  stale?: boolean;
  onSelect: (date: Date) => void;
  onChangeMonth: (delta: number) => void;
  onToday: () => void;
};

export function MonthGrid({ year, month, selected, eventsByDay, stale, onSelect, onChangeMonth, onToday }: MonthGridProps) {
  const theme = useTheme();
  const [width, setWidth] = useState(0);
  // +1 when moving forward a month, -1 backward. A shared value (not state)
  // so the outgoing page's exiting worklet reads the direction of the move
  // that's unmounting it, not the one from its last render.
  const direction = useSharedValue(1);

  const today = new Date();
  const todayParts = wibParts(today);
  const showToday = todayParts.year !== year || todayParts.month !== month || !isSameWibDay(selected, today);

  const changeMonth = (delta: number) => {
    direction.value = delta;
    Haptics.selectionAsync().catch(() => {});
    onChangeMonth(delta);
  };

  const selectDay = (date: Date) => {
    const target = wibParts(date);
    const delta = target.year * 12 + target.month - (year * 12 + month);
    if (delta !== 0) direction.value = Math.sign(delta);
    onSelect(date);
  };

  const pan = Gesture.Pan()
    .runOnJS(true)
    .activeOffsetX([-16, 16])
    .failOffsetY([-12, 12])
    .onEnd((e) => {
      if (Math.abs(e.translationX) > SWIPE_DISTANCE || Math.abs(e.velocityX) > SWIPE_VELOCITY) {
        changeMonth(e.translationX < 0 ? 1 : -1);
      }
    });

  return (
    <Stack gap={3}>
      <HStack align="center" justify="space-between">
        <Animated.View key={`${year}-${month}`} entering={FadeIn.duration(motion.duration.base)}>
          <Text variant="title" accessibilityRole="header">
            {formatMonthTitle(year, month)}
          </Text>
        </Animated.View>
        <HStack align="center" gap={1}>
          {showToday ? (
            <Animated.View entering={FadeIn.duration(motion.duration.fast)} exiting={FadeOut.duration(motion.duration.fast)}>
              <PressableScale
                onPress={() => {
                  const target = wibParts(new Date());
                  direction.value = target.year * 12 + target.month >= year * 12 + month ? 1 : -1;
                  onToday();
                }}
                accessibilityRole="button"
                accessibilityLabel="Jump to today"
              >
                <Stack py={1.5} px={3} radius="pill" bg={theme.colors.accentRamp[900]}>
                  <Text variant="meta" tone="accent" style={{ fontFamily: theme.fontFamily.medium }}>
                    Today
                  </Text>
                </Stack>
              </PressableScale>
            </Animated.View>
          ) : null}
          <PressableScale onPress={() => changeMonth(-1)} accessibilityRole="button" accessibilityLabel="Previous month" hitSlop={6}>
            <Stack p={2}>
              <CaretLeft size={20} color={theme.colors.text} />
            </Stack>
          </PressableScale>
          <PressableScale onPress={() => changeMonth(1)} accessibilityRole="button" accessibilityLabel="Next month" hitSlop={6}>
            <Stack p={2}>
              <CaretRight size={20} color={theme.colors.text} />
            </Stack>
          </PressableScale>
        </HStack>
      </HStack>

      <HStack>
        {WEEKDAY_LABELS.map((label, i) => (
          <Text key={i} variant="caption" tone={i >= 5 ? "faint" : "muted"} align="center" style={{ flex: 1, fontFamily: theme.fontFamily.medium }}>
            {label}
          </Text>
        ))}
      </HStack>

      <GestureDetector gesture={pan}>
        <View
          onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
          style={{ height: CELL_HEIGHT * 6, overflow: "hidden", opacity: stale ? 0.55 : 1 }}
        >
          <MonthPage
            key={`${year}-${month}`}
            year={year}
            month={month}
            width={width}
            selected={selected}
            eventsByDay={eventsByDay}
            direction={direction}
            onSelect={selectDay}
          />
        </View>
      </GestureDetector>
    </Stack>
  );
}

type MonthPageProps = {
  year: number;
  month: number;
  width: number;
  selected: Date;
  eventsByDay: Map<string, CalendarEvent[]>;
  direction: SharedValue<number>;
  onSelect: (date: Date) => void;
};

/** One month's 6×7 grid. Keyed by month, so a month change unmounts this
 *  page (sliding out) while the next one slides in from the swipe side. */
function MonthPage({ year, month, width, selected, eventsByDay, direction, onSelect }: MonthPageProps) {
  const theme = useTheme();
  const weeks = useMemo(() => monthMatrix(year, month), [year, month]);
  const todayKey = wibDayKey(new Date());
  const selectedKey = wibDayKey(selected);
  const cellWidth = width / 7;

  const entering: EntryExitAnimationFunction = () => {
    "worklet";
    const config = { duration: motion.duration.slow, easing: easing.out };
    return {
      initialValues: { opacity: 0, transform: [{ translateX: direction.value * SLIDE_DISTANCE }] },
      animations: { opacity: withTiming(1, config), transform: [{ translateX: withTiming(0, config) }] },
    };
  };
  const exiting: EntryExitAnimationFunction = () => {
    "worklet";
    const config = { duration: motion.duration.base, easing: easing.out };
    return {
      initialValues: { opacity: 1, transform: [{ translateX: 0 }] },
      animations: { opacity: withTiming(0, config), transform: [{ translateX: withTiming(-direction.value * SLIDE_DISTANCE, config) }] },
    };
  };

  let selectedCell: { row: number; col: number } | null = null;
  weeks.forEach((week, row) =>
    week.forEach((date, col) => {
      if (wibDayKey(date) === selectedKey) selectedCell = { row, col };
    }),
  );

  return (
    <Animated.View entering={entering} exiting={exiting} style={{ position: "absolute", top: 0, left: 0, right: 0 }}>
      {width > 0 && selectedCell ? <SelectionPill cell={selectedCell} cellWidth={cellWidth} /> : null}
      {weeks.map((week, row) => (
        <HStack key={row} style={{ height: CELL_HEIGHT }}>
          {week.map((date) => {
            const key = wibDayKey(date);
            return (
              <DayCell
                key={key}
                date={date}
                inMonth={wibParts(date).month === month}
                isToday={key === todayKey}
                isSelected={key === selectedKey}
                eventCount={eventsByDay.get(key)?.length ?? 0}
                onSelect={onSelect}
                accent={theme.colors.accent}
              />
            );
          })}
        </HStack>
      ))}
    </Animated.View>
  );
}

/** The filled accent circle behind the selected day. Springs between cells
 *  rather than jumping, with a small scale "pop" on landing. */
function SelectionPill({ cell, cellWidth }: { cell: { row: number; col: number }; cellWidth: number }) {
  const theme = useTheme();
  const targetX = cell.col * cellWidth + (cellWidth - PILL_SIZE) / 2;
  const targetY = cell.row * CELL_HEIGHT + PILL_TOP;
  const x = useSharedValue(targetX);
  const y = useSharedValue(targetY);
  const scale = useSharedValue(1);

  useEffect(() => {
    if (x.value === targetX && y.value === targetY) return;
    x.value = withSpring(targetX, motion.spring);
    y.value = withSpring(targetY, motion.spring);
    scale.value = withSequence(withTiming(0.82, { duration: motion.duration.fast, easing: easing.out }), withSpring(1, motion.spring));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetX, targetY]);

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: x.value }, { translateY: y.value }, { scale: scale.value }],
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        { position: "absolute", top: 0, left: 0, width: PILL_SIZE, height: PILL_SIZE, borderRadius: PILL_SIZE / 2, backgroundColor: theme.colors.accent },
        style,
      ]}
    />
  );
}

type DayCellProps = {
  date: Date;
  inMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  eventCount: number;
  accent: string;
  onSelect: (date: Date) => void;
};

const DayCell = memo(function DayCell({ date, inMonth, isToday, isSelected, eventCount, accent, onSelect }: DayCellProps) {
  const theme = useTheme();
  const { day } = wibParts(date);
  const dots = Math.min(eventCount, MAX_DOTS);

  const textColor = isSelected ? theme.colors.bg : isToday ? accent : inMonth ? theme.colors.text : theme.colors.neutral[600];
  const dotColor = inMonth ? accent : theme.colors.neutral[700];

  return (
    <Pressable
      style={{ flex: 1, alignItems: "center" }}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onSelect(date);
      }}
      accessibilityRole="button"
      accessibilityState={{ selected: isSelected }}
      accessibilityLabel={`${day}${isToday ? ", today" : ""}${eventCount ? `, ${eventCount} event${eventCount === 1 ? "" : "s"}` : ""}`}
    >
      <View
        style={{
          marginTop: PILL_TOP,
          width: PILL_SIZE,
          height: PILL_SIZE,
          borderRadius: PILL_SIZE / 2,
          alignItems: "center",
          justifyContent: "center",
          borderWidth: isToday && !isSelected ? 1.5 : 0,
          borderColor: accent,
        }}
      >
        <Text
          variant="body"
          numeric
          style={{ color: textColor, fontFamily: isSelected || isToday ? theme.fontFamily.bold : theme.fontFamily.regular }}
        >
          {day}
        </Text>
      </View>
      <HStack gap={0.5} style={{ marginTop: theme.spacing[1], height: 5 }}>
        {Array.from({ length: dots }, (_, i) => (
          <Animated.View
            key={i}
            entering={FadeIn.delay(i * motion.staggerStep).duration(motion.duration.base)}
            style={{ width: 5, height: 5, borderRadius: theme.radius.full, backgroundColor: dotColor }}
          />
        ))}
      </HStack>
    </Pressable>
  );
});
