import { useEffect } from "react";
import Animated, { useAnimatedStyle, useSharedValue, withDelay, withRepeat, withTiming } from "react-native-reanimated";

import { HStack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

function Dot({ color, delay }: { color: string; delay: number }) {
  const theme = useTheme();
  const opacity = useSharedValue(0.3);

  useEffect(() => {
    opacity.value = withDelay(delay, withRepeat(withTiming(1, { duration: 450 }), -1, true));
  }, [delay, opacity]);

  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return <Animated.View style={[{ width: 6, height: 6, borderRadius: theme.radius.full, backgroundColor: color }, style]} />;
}

export function TypingIndicator() {
  const theme = useTheme();

  return (
    <HStack
      align="center"
      gap={1.5}
      py={3}
      px={4}
      bg={theme.colors.surface}
      elevationLevel="sm"
      style={{
        alignSelf: "flex-start",
        borderTopLeftRadius: theme.radius.lg,
        borderTopRightRadius: theme.radius.lg,
        borderBottomRightRadius: theme.radius.lg,
        borderBottomLeftRadius: theme.radius.sm,
      }}
      accessibilityLabel="Assistant is typing"
    >
      <Dot color={theme.colors.neutral[500]} delay={0} />
      <Dot color={theme.colors.neutral[600]} delay={150} />
      <Dot color={theme.colors.neutral[700]} delay={300} />
    </HStack>
  );
}
