// Token-only layout & text primitives. This is the mechanism that's supposed
// to make the token system actually get used this time: writing `<Box p="4">`
// is less code than hand-rolling `style={{ padding: 16 }}`, so there's no
// reason to reach for a raw number. The ESLint rule (eslint-rules/no-raw-style-values.js)
// backs this up by banning numeric padding/margin/gap/fontSize/borderRadius
// and raw hex colors in `style` props outside this file and tokens.ts.
import type { ReactNode } from "react";
import {
  Text as RNText,
  View,
  type StyleProp,
  type TextProps as RNTextProps,
  type TextStyle,
  type ViewProps,
  type ViewStyle,
} from "react-native";

import { useTheme, type Theme } from "./ThemeProvider";
import type { SpacingKey } from "./tokens";

type RadiusKey = keyof Theme["radius"];
type TypeVariant = keyof Theme["type"];
type NumericVariant = keyof Theme["numericType"];
export type Tone = "primary" | "secondary" | "muted" | "faint" | "accent" | "positive" | "negative" | "tight" | "inverse";

export interface BoxProps extends Omit<ViewProps, "style"> {
  children?: ReactNode;
  p?: SpacingKey;
  px?: SpacingKey;
  py?: SpacingKey;
  pt?: SpacingKey;
  pb?: SpacingKey;
  pl?: SpacingKey;
  pr?: SpacingKey;
  m?: SpacingKey;
  mx?: SpacingKey;
  my?: SpacingKey;
  mt?: SpacingKey;
  mb?: SpacingKey;
  ml?: SpacingKey;
  mr?: SpacingKey;
  gap?: SpacingKey;
  rowGap?: SpacingKey;
  columnGap?: SpacingKey;
  row?: boolean;
  reverse?: boolean;
  wrap?: boolean;
  align?: ViewStyle["alignItems"];
  justify?: ViewStyle["justifyContent"];
  flex?: number;
  bg?: string;
  radius?: RadiusKey;
  elevationLevel?: "sm" | "md" | "lg";
  style?: StyleProp<ViewStyle>;
}

export function Box({
  children,
  p,
  px,
  py,
  pt,
  pb,
  pl,
  pr,
  m,
  mx,
  my,
  mt,
  mb,
  ml,
  mr,
  gap,
  rowGap,
  columnGap,
  row,
  reverse,
  wrap,
  align,
  justify,
  flex,
  bg,
  radius: radiusKey,
  elevationLevel,
  style,
  ...rest
}: BoxProps) {
  const theme = useTheme();
  const s = theme.spacing;

  const resolved: ViewStyle = {
    ...(p !== undefined && { padding: s[p] }),
    ...(px !== undefined && { paddingHorizontal: s[px] }),
    ...(py !== undefined && { paddingVertical: s[py] }),
    ...(pt !== undefined && { paddingTop: s[pt] }),
    ...(pb !== undefined && { paddingBottom: s[pb] }),
    ...(pl !== undefined && { paddingLeft: s[pl] }),
    ...(pr !== undefined && { paddingRight: s[pr] }),
    ...(m !== undefined && { margin: s[m] }),
    ...(mx !== undefined && { marginHorizontal: s[mx] }),
    ...(my !== undefined && { marginVertical: s[my] }),
    ...(mt !== undefined && { marginTop: s[mt] }),
    ...(mb !== undefined && { marginBottom: s[mb] }),
    ...(ml !== undefined && { marginLeft: s[ml] }),
    ...(mr !== undefined && { marginRight: s[mr] }),
    ...(gap !== undefined && { gap: s[gap] }),
    ...(rowGap !== undefined && { rowGap: s[rowGap] }),
    ...(columnGap !== undefined && { columnGap: s[columnGap] }),
    ...(row !== undefined && {
      flexDirection: row ? (reverse ? "row-reverse" : "row") : reverse ? "column-reverse" : "column",
    }),
    ...(wrap !== undefined && { flexWrap: wrap ? "wrap" : "nowrap" }),
    ...(align !== undefined && { alignItems: align }),
    ...(justify !== undefined && { justifyContent: justify }),
    ...(flex !== undefined && { flex }),
    ...(bg !== undefined && { backgroundColor: bg }),
    ...(radiusKey !== undefined && { borderRadius: theme.radius[radiusKey] }),
    ...(elevationLevel !== undefined && theme.elevation[elevationLevel]),
  };

  return (
    <View style={[resolved, style]} {...rest}>
      {children}
    </View>
  );
}

export type StackProps = Omit<BoxProps, "row">;

/** Vertical flex layout — Box with flexDirection: column. */
export function Stack(props: StackProps) {
  return <Box row={false} {...props} />;
}

/** Horizontal flex layout — Box with flexDirection: row. */
export function HStack(props: StackProps) {
  return <Box row {...props} />;
}

function toneColor(theme: Theme, tone: Tone): string {
  switch (tone) {
    case "primary":
      return theme.colors.text;
    case "secondary":
      return theme.colors.neutral[300];
    case "muted":
      return theme.colors.neutral[500];
    case "faint":
      return theme.colors.neutral[600];
    case "accent":
      return theme.colors.accent;
    case "positive":
      return theme.status.comfortable;
    case "negative":
      return theme.status.short;
    case "tight":
      return theme.status.tight;
    case "inverse":
      return theme.colors.bg;
  }
}

function isNumericVariant(theme: Theme, variant: TypeVariant): variant is NumericVariant {
  return variant in theme.numericType;
}

export interface TextProps extends Omit<RNTextProps, "style"> {
  children?: ReactNode;
  variant?: TypeVariant;
  tone?: Tone;
  /** Tabular-figure rendering for IDR amounts and other values that must not jitter width. */
  numeric?: boolean;
  align?: TextStyle["textAlign"];
  style?: StyleProp<TextStyle>;
}

export function Text({ children, variant = "body", tone = "primary", numeric, align, style, ...rest }: TextProps) {
  const theme = useTheme();
  const base: TextStyle = numeric && isNumericVariant(theme, variant) ? theme.numericType[variant] : theme.type[variant];

  return (
    <RNText style={[base, { color: toneColor(theme, tone) }, align !== undefined && { textAlign: align }, style]} {...rest}>
      {children}
    </RNText>
  );
}
