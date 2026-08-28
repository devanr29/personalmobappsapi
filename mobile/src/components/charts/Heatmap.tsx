// Magnitude-by-day calendar grid (spend density). Sequential — one hue,
// more-is-darker, drawn from the validated accentRamp ordinal ramp
// (theme.chart.sequential). Never a second hue for "more spend."
//
// Wraps into fixed-width columns (default 7, one calendar week) instead of
// a single non-wrapping row — 31 cells at 20px+gaps is 620px+, wider than
// a phone screen, so a plain row clipped most of the month.
import { View } from "react-native";

import { mark } from "./geometry";
import { Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export interface HeatmapCell {
  date: string;
  label: string;
  /** Monday=0..Sunday=6 — leading empty cells align the grid to a real week. */
  weekday: number;
  /** Magnitude driving the color — e.g. spend, not transaction count. */
  value: number;
  count: number;
}

export interface HeatmapProps {
  cells: HeatmapCell[];
  maxValue?: number;
  columns?: number;
  cellSize?: number;
  /** Formats a cell's value for the accessibility label — defaults to the
   * raw number (fine for a count); pass formatRupiah for a spend heatmap. */
  formatValue?: (value: number) => string;
}

export function Heatmap({ cells, maxValue, columns = 7, cellSize = 32, formatValue }: HeatmapProps) {
  const theme = useTheme();
  const ramp = theme.chart.sequential;
  const max = maxValue ?? Math.max(1, ...cells.map((c) => c.value));
  const label = formatValue ?? ((v: number) => String(v));

  function colorFor(value: number): string {
    if (value <= 0) return theme.chart.track;
    const step = Math.min(ramp.length - 1, Math.max(0, Math.ceil((value / max) * ramp.length) - 1));
    return ramp[step];
  }

  const leadingBlanks = cells.length > 0 ? cells[0].weekday : 0;
  const items: (HeatmapCell | null)[] = [...Array(leadingBlanks).fill(null), ...cells];

  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", width: columns * (cellSize + mark.surfaceGap), gap: mark.surfaceGap }}>
      {items.map((cell, i) =>
        cell ? (
          <View
            key={cell.date}
            style={{ width: cellSize, height: cellSize, alignItems: "center", justifyContent: "center" }}
            accessible
            accessibilityLabel={`${cell.date}: ${label(cell.value)}, ${cell.count} transaction${cell.count === 1 ? "" : "s"}`}
          >
            <View
              style={{
                width: cellSize,
                height: cellSize,
                borderRadius: mark.barEndRadius,
                backgroundColor: colorFor(cell.value),
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text variant="caption" tone={cell.value > 0 ? "inverse" : "faint"}>
                {cell.label}
              </Text>
            </View>
          </View>
        ) : (
          <View key={`blank-${i}`} style={{ width: cellSize, height: cellSize }} />
        ),
      )}
    </View>
  );
}
