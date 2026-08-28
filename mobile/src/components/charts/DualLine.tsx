// Two sloped lines sharing one scale (e.g. actual spend vs an ideal
// straight-line pace). LineVsBaseline only draws one line plus a *flat*
// baseline (y1 === y2) and can't express this — both series here can move.
// Per the mark spec: the reference/ideal line is solid, never dashed.
import { useMemo } from "react";
import Svg, { Circle, Path } from "react-native-svg";

import { mark } from "./geometry";
import { useTheme } from "@/theme/ThemeProvider";

export interface DualLineProps {
  actual: number[];
  ideal: number[];
  width?: number;
  height?: number;
  actualColor?: string;
  idealColor?: string;
}

function buildLinePath(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
}

export function DualLine({ actual, ideal, width = 280, height = 120, actualColor, idealColor }: DualLineProps) {
  const theme = useTheme();
  const stroke = actualColor ?? theme.colors.accent;
  const refStroke = idealColor ?? theme.chart.axis;

  const geometry = useMemo(() => {
    const n = Math.min(actual.length, ideal.length);
    if (n === 0) return null;
    const values = [...actual.slice(0, n), ...ideal.slice(0, n)];
    const min = Math.min(...values, 0);
    const max = Math.max(...values);
    const range = max - min || 1;
    const padY = mark.markerRadius;
    const usableH = height - padY * 2;
    const toY = (v: number) => padY + usableH - ((v - min) / range) * usableH;
    const toX = (i: number) => (n === 1 ? width : (i / (n - 1)) * width);

    const actualPoints = actual.slice(0, n).map((v, i) => ({ x: toX(i), y: toY(v) }));
    const idealPoints = ideal.slice(0, n).map((v, i) => ({ x: toX(i), y: toY(v) }));
    const last = actualPoints[actualPoints.length - 1];
    return {
      actualLine: buildLinePath(actualPoints),
      idealLine: buildLinePath(idealPoints),
      last,
    };
  }, [actual, ideal, width, height]);

  if (!geometry) return null;

  return (
    <Svg width={width} height={height}>
      <Path
        d={geometry.idealLine}
        stroke={refStroke}
        strokeWidth={mark.axisWidth}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Path
        d={geometry.actualLine}
        stroke={stroke}
        strokeWidth={mark.lineWidth}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Circle cx={geometry.last.x} cy={geometry.last.y} r={mark.markerRadius + mark.surfaceRingWidth} fill={theme.colors.surface} />
      <Circle cx={geometry.last.x} cy={geometry.last.y} r={mark.markerRadius} fill={stroke} />
    </Svg>
  );
}
