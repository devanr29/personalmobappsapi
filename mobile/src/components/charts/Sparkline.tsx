// Inline trend line for a stat tile. Single series — no legend needed (the
// tile's own label names it). End marker gets a surface-color ring so it
// stays legible where the line runs under it.
import { useMemo } from "react";
import { View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";

import { mark } from "./geometry";
import { useTheme } from "@/theme/ThemeProvider";

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  showArea?: boolean;
  showEndMarker?: boolean;
}

function buildLinePath(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
}

export function Sparkline({ data, width = 64, height = 24, color, showArea = true, showEndMarker = true }: SparklineProps) {
  const theme = useTheme();
  const stroke = color ?? theme.colors.accent;

  const geometry = useMemo(() => {
    if (data.length === 0) return null;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padY = mark.markerRadius;
    const usableH = height - padY * 2;
    const points = data.map((v, i) => ({
      x: data.length === 1 ? width : (i / (data.length - 1)) * width,
      y: padY + usableH - ((v - min) / range) * usableH,
    }));
    const line = buildLinePath(points);
    const last = points[points.length - 1];
    const area = `${line} L${last.x.toFixed(2)},${height} L${points[0].x.toFixed(2)},${height} Z`;
    return { line, area, last };
  }, [data, width, height]);

  if (!geometry) return null;

  return (
    <View style={{ width, height }}>
      <Svg width={width} height={height}>
        {showArea ? <Path d={geometry.area} fill={stroke} opacity={mark.areaOpacity} /> : null}
        <Path d={geometry.line} stroke={stroke} strokeWidth={mark.lineWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        {showEndMarker ? (
          <>
            <Circle cx={geometry.last.x} cy={geometry.last.y} r={mark.markerRadius + mark.surfaceRingWidth} fill={theme.colors.surface} />
            <Circle cx={geometry.last.x} cy={geometry.last.y} r={mark.markerRadius} fill={stroke} />
          </>
        ) : null}
      </Svg>
    </View>
  );
}
