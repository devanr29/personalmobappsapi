// Emphasis form: one series in the accent hue against a solid neutral
// baseline (never dashed — see mark spec). General-purpose; not currently
// wired to fabricated data anywhere in the app (the backend has no
// time-series spend log, only point-in-time snapshots) — kept for when a
// real series exists (e.g. a future daily-spend history endpoint).
import { useMemo } from "react";
import Svg, { Line as SvgLine, Path } from "react-native-svg";

import { mark } from "./geometry";
import { useTheme } from "@/theme/ThemeProvider";

export interface LineVsBaselineProps {
  data: number[];
  baseline: number;
  width?: number;
  height?: number;
  color?: string;
}

export function LineVsBaseline({ data, baseline, width = 240, height = 80, color }: LineVsBaselineProps) {
  const theme = useTheme();
  const stroke = color ?? theme.colors.accent;

  const geometry = useMemo(() => {
    if (data.length === 0) return null;
    const values = [...data, baseline];
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const padY = mark.markerRadius;
    const usableH = height - padY * 2;
    const toY = (v: number) => padY + usableH - ((v - min) / range) * usableH;
    const points = data.map((v, i) => ({
      x: data.length === 1 ? width : (i / (data.length - 1)) * width,
      y: toY(v),
    }));
    const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
    return { line, baselineY: toY(baseline) };
  }, [data, baseline, width, height]);

  if (!geometry) return null;

  return (
    <Svg width={width} height={height}>
      <SvgLine x1={0} y1={geometry.baselineY} x2={width} y2={geometry.baselineY} stroke={theme.chart.axis} strokeWidth={mark.axisWidth} />
      <Path d={geometry.line} stroke={stroke} strokeWidth={mark.lineWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
