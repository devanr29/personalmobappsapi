// Vertical column chart — month/period-over-period spend, the one form
// the other seven primitives don't cover. Plain Views, not SVG: columns
// are rectangles needing real text (axis ticks, tap readout) and a full-
// height touch target, and flex:1 slots give the x-scale for free with
// no width prop and no onLayout measurement (matches Meter/StackedBar/
// Heatmap's split, not Sparkline/DualLine/LineVsBaseline's).
//
// Fit-to-width, never horizontally scrollable — a nested horizontal
// scroll inside the screen's vertical ScrollView is an Android gesture
// trap, and the whole point of a 12-month chart is at-a-glance
// comparison, which a scroll would hide half of.
import { useState } from "react";
import { Pressable, View } from "react-native";

import { clamp01, columnScale, labelStrideFor, mark } from "./geometry";
import { Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export interface ColumnDatum {
  /** Stable React key. */
  key: string;
  /** Full label for a11y and the tap readout, e.g. "Jul 2026". */
  label: string;
  /** Axis tick, e.g. "Jul". */
  shortLabel: string;
  /** Non-negative. Negative values are clamped to 0 — this chart doesn't
   * support a zero-crossing axis. */
  value: number;
  /** The current, still-accruing bucket — rendered dimmed. */
  isPartial?: boolean;
}

export interface ColumnChartProps {
  data: ColumnDatum[];
  /** Plot band height only; the label row and gutter sit around it. */
  height?: number;
  /** Solid reference line (e.g. average spend). Omit to hide it. */
  baseline?: number;
  baselineLabel?: string;
  /** Full-precision formatter, used for a11y labels and axis extremes. */
  formatValue: (value: number) => string;
  /** Compact formatter for the gutter ticks; defaults to formatValue. */
  formatAxisValue?: (value: number) => string;
  color?: string;
  showValueAxis?: boolean;
  /** Override the automatic label-thinning stride. */
  labelStride?: number;
  selectedIndex?: number | null;
  onSelect?: (index: number) => void;
}

export function ColumnChart({
  data,
  height = 132,
  baseline,
  baselineLabel,
  formatValue,
  formatAxisValue,
  color,
  showValueAxis = true,
  labelStride,
  selectedIndex,
  onSelect,
}: ColumnChartProps) {
  const theme = useTheme();
  const [pressedIndex, setPressedIndex] = useState<number | null>(null);

  if (data.length === 0) return null;

  const fill = color ?? theme.colors.accent;
  const axisFormat = formatAxisValue ?? formatValue;
  const { max } = columnScale(
    data.map((d) => Math.max(0, d.value)),
    baseline,
  );
  const stride = labelStride ?? labelStrideFor(data.length);
  const showLabelAt = (i: number) => (data.length - 1 - i) % stride === 0;
  const gutter = showValueAxis ? mark.axisGutter : 0;

  const baselineY = baseline !== undefined ? height - clamp01(baseline / max) * height : null;
  const zeroTickY = height;
  const maxTickY = 0;
  const captionLineHeight = theme.type.caption.lineHeight ?? 14;
  // Suppress the baseline gutter label when it would overlap the 0 or
  // max tick — three stacked ticks inside ~132pt reads as noise.
  const baselineCollides =
    baselineY !== null && (Math.abs(baselineY - zeroTickY) < captionLineHeight || Math.abs(baselineY - maxTickY) < captionLineHeight);

  return (
    <View>
      <View style={{ flexDirection: "row", height }}>
        {showValueAxis ? (
          <View style={{ width: gutter, height }}>
            <Text variant="caption" tone="faint" style={{ position: "absolute", top: 0 }}>
              {axisFormat(max)}
            </Text>
            <Text variant="caption" tone="faint" style={{ position: "absolute", bottom: 0 }}>
              {axisFormat(0)}
            </Text>
            {baselineY !== null && !baselineCollides ? (
              <Text
                variant="caption"
                tone="muted"
                style={{ position: "absolute", top: baselineY - captionLineHeight / 2 }}
              >
                {baselineLabel ?? axisFormat(baseline as number)}
              </Text>
            ) : null}
          </View>
        ) : null}

        <View style={{ flex: 1, position: "relative" }}>
          {baselineY !== null ? (
            <View
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: baselineY,
                height: mark.axisWidth,
                backgroundColor: theme.chart.axis,
              }}
            />
          ) : null}

          <View style={{ flex: 1, flexDirection: "row", alignItems: "flex-end", gap: mark.surfaceGap }}>
            {data.map((d, i) => (
              <ColumnSlot
                key={d.key}
                datum={d}
                height={height}
                max={max}
                color={fill}
                formatValue={formatValue}
                selected={selectedIndex === i}
                pressed={pressedIndex === i}
                onPress={
                  onSelect
                    ? () => {
                        setPressedIndex(i);
                        onSelect(i);
                      }
                    : undefined
                }
              />
            ))}
          </View>

          <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: mark.axisWidth, backgroundColor: theme.chart.axis }} />
        </View>
      </View>

      <View style={{ flexDirection: "row" }}>
        {showValueAxis ? <View style={{ width: gutter }} /> : null}
        <View style={{ flex: 1, flexDirection: "row", gap: mark.surfaceGap }}>
          {data.map((d, i) => (
            <View key={d.key} style={{ flex: 1, maxWidth: mark.barThicknessMax, alignItems: "center" }}>
              <Text variant="caption" tone={d.isPartial ? "accent" : "muted"} numberOfLines={1} align="center">
                {showLabelAt(i) ? d.shortLabel : ""}
              </Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

function ColumnSlot({
  datum,
  height,
  max,
  color,
  formatValue,
  selected,
  pressed,
  onPress,
}: {
  datum: ColumnDatum;
  height: number;
  max: number;
  color: string;
  formatValue: (value: number) => string;
  selected: boolean;
  pressed: boolean;
  onPress?: () => void;
}) {
  const value = Math.max(0, datum.value);
  // Floored at lineWidth when there's any real spend, so a tiny nonzero
  // month is never an invisible 0px column.
  const columnHeight = value > 0 ? Math.max(mark.lineWidth, clamp01(value / max) * height) : 0;
  const opacity = datum.isPartial ? mark.partialOpacity : selected || pressed ? 1 : 0.85;
  const a11yLabel = `${datum.label}: ${formatValue(value)}${datum.isPartial ? ", in progress" : ""}`;

  // No flex/width here — the outer wrapper (View or Pressable, both set
  // flex:1 + maxWidth) owns sizing; this just stretches to fill it via
  // the default alignItems:"stretch" cross-axis behavior. An explicit
  // `height` alongside its own `flex` would fight Yoga's layout solver.
  const column = (
    <View style={{ height, justifyContent: "flex-end", alignItems: "center" }}>
      <View
        style={{
          width: "100%",
          height: columnHeight,
          backgroundColor: color,
          opacity,
          borderTopLeftRadius: mark.barEndRadius,
          borderTopRightRadius: mark.barEndRadius,
        }}
      />
      {datum.isPartial && columnHeight > 0 ? (
        <View
          style={{
            position: "absolute",
            bottom: columnHeight - mark.lineWidth,
            width: "100%",
            height: mark.lineWidth,
            backgroundColor: color,
            borderRadius: mark.lineWidth / 2,
          }}
        />
      ) : null}
      {selected ? (
        <View
          style={{
            position: "absolute",
            bottom: -mark.surfaceGap - mark.lineWidth,
            width: mark.markerRadius,
            height: mark.markerRadius,
            borderRadius: mark.markerRadius / 2,
            backgroundColor: color,
          }}
        />
      ) : null}
    </View>
  );

  if (!onPress) {
    return (
      <View accessible accessibilityLabel={a11yLabel} style={{ flex: 1, maxWidth: mark.barThicknessMax }}>
        {column}
      </View>
    );
  }

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={a11yLabel}
      accessibilityState={{ selected }}
      style={{ flex: 1, maxWidth: mark.barThicknessMax }}
    >
      {column}
    </Pressable>
  );
}
