import { useMemo } from "react";
import { StyleSheet, type ViewStyle, type TextStyle, type ImageStyle } from "react-native";

import { useTheme, type Theme } from "./ThemeProvider";

type NamedStyles<T> = { [P in keyof T]: ViewStyle | TextStyle | ImageStyle };

/**
 * `const styles = useStyles((t) => ({ row: { flexDirection: "row", gap: t.spacing[2] } }))`
 *
 * Restores `StyleSheet.create` for layouts the <Box>/<Stack>/<Text> primitives
 * don't cover, without losing access to the theme at definition time — the
 * reason v1 gave up on StyleSheet.create almost everywhere. Recomputes only
 * when the theme identity changes (accent/ground/corner), not on every render.
 */
export function useStyles<T extends NamedStyles<T>>(makeStyles: (theme: Theme) => T): T {
  const theme = useTheme();
  // makeStyles is expected to be a pure function of theme, defined inline at
  // the call site — intentionally excluded from deps so callers don't need
  // to useCallback it themselves.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => StyleSheet.create(makeStyles(theme)), [theme]);
}
