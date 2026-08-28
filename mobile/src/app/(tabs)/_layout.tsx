import { CalendarBlank, ChatCircleDots, House, SquaresFour, Wallet } from "phosphor-react-native";
import { Tabs, TabList, TabSlot, TabTrigger } from "expo-router/ui";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { GlassSurface } from "@/components/GlassSurface";
import { TabButton } from "@/components/tabs/TabButton";
import { HStack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export default function TabLayout() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();

  return (
    <Tabs>
      <View style={{ flex: 1, backgroundColor: theme.colors.bg }}>
        <TabSlot />
      </View>
      <TabList style={{ display: "none" }}>
        <TabTrigger name="index" href="/" />
        <TabTrigger name="chat" href="/chat" />
        <TabTrigger name="calendar" href="/calendar" />
        <TabTrigger name="budget" href="/budget" />
        <TabTrigger name="more" href="/more" />
      </TabList>
      <GlassSurface style={{ borderTopWidth: 1, borderTopColor: theme.colors.divider }}>
        <HStack style={{ paddingBottom: insets.bottom }}>
          <TabTrigger name="index" asChild>
            <TabButton IconComponent={House} label="Home" />
          </TabTrigger>
          <TabTrigger name="chat" asChild>
            <TabButton IconComponent={ChatCircleDots} label="Chat" />
          </TabTrigger>
          <TabTrigger name="calendar" asChild>
            <TabButton IconComponent={CalendarBlank} label="Calendar" />
          </TabTrigger>
          <TabTrigger name="budget" asChild>
            <TabButton IconComponent={Wallet} label="Budget" />
          </TabTrigger>
          <TabTrigger name="more" asChild>
            <TabButton IconComponent={SquaresFour} label="More" />
          </TabTrigger>
        </HStack>
      </GlassSurface>
    </Tabs>
  );
}
