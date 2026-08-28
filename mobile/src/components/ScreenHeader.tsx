import { useRouter } from "expo-router";
import { CaretLeft } from "phosphor-react-native";
import { Pressable } from "react-native";
import Animated, { useAnimatedStyle, type SharedValue } from "react-native-reanimated";

import { GlassSurface } from "@/components/GlassSurface";
import { HStack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type ScreenHeaderProps = {
  title: string;
  /**
   * Reanimated scroll offset from the owning screen. When provided, the
   * bottom hairline fades in as content passes under the header instead of
   * always being visible — the glass surface itself never animates opacity
   * (see GlassSurface caveat).
   */
  scrollY?: SharedValue<number>;
};

export function ScreenHeader({ title, scrollY }: ScreenHeaderProps) {
  const theme = useTheme();
  const router = useRouter();

  const dividerStyle = useAnimatedStyle(() => ({
    opacity: scrollY ? Math.min(1, Math.max(0, scrollY.value / 24)) : 1,
  }));

  return (
    <GlassSurface style={{ borderBottomWidth: 0 }}>
      <HStack align="center" gap={2} px={4} py={3}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Go back" hitSlop={8}>
          <CaretLeft size={20} color={theme.colors.text} />
        </Pressable>
        <Text variant="cardTitle">{title}</Text>
      </HStack>
      <Animated.View
        style={[
          { position: "absolute", left: 0, right: 0, bottom: 0, height: 1, backgroundColor: theme.colors.divider },
          dividerStyle,
        ]}
      />
    </GlassSurface>
  );
}
