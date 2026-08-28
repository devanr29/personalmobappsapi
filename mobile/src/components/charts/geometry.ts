// Fixed mark-spec constants shared by every chart in src/components/charts/.
// These are universal chart-anatomy rules (dataviz skill), not brand tokens —
// they don't change with accent/ground/corner theme config, so they live
// here rather than in theme/tokens.ts. This folder is exempt from the
// no-raw-style-values ESLint rule for exactly this reason.
export const mark = {
  barThickness: 8,
  barThicknessMax: 24,
  barEndRadius: 4,
  lineWidth: 2,
  markerMinDiameter: 8,
  markerRadius: 4,
  areaOpacity: 0.1,
  surfaceGap: 2,
  surfaceRingWidth: 2,
  axisWidth: 1,
  // The in-progress/current bucket in a column chart can't get a second
  // hue (categorical is capped at 2, both slots already spoken for by
  // other budget charts) — it gets the same accent at reduced opacity
  // instead. Lightness-only differentiation survives CVD.
  partialOpacity: 0.45,
  // Left gutter width for a chart's value axis (two ticks: max and 0).
  axisGutter: 48,
} as const;

export function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/** Linear-from-zero scale for a column chart: the top of the plot area is
 * whichever is larger, the tallest value or the baseline reference line
 * (a baseline above every column must still be visible), floored at 1 so
 * an all-zero dataset never divides by zero. */
export function columnScale(values: number[], baseline?: number): { max: number } {
  const tallest = values.reduce((m, v) => Math.max(m, v), 0);
  return { max: Math.max(1, tallest, baseline ?? 0) };
}

/** How many buckets to skip between visible axis labels, anchored on the
 * last (most recent) bucket so the current/partial one always keeps its
 * label. n<=7 shows every label; larger n thins to every other. */
export function labelStrideFor(n: number): number {
  return n <= 7 ? 1 : 2;
}
