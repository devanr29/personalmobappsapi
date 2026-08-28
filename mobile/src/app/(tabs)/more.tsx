import { useRouter } from "expo-router";
import {
  Alarm,
  Brain,
  GearSix,
  Lightbulb,
  MagnifyingGlass,
  Newspaper,
  Note,
  type Icon,
} from "phosphor-react-native";
import { ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ShortcutTile } from "@/components/ShortcutTile";
import { AnimatedListItem } from "@/theme/motion";
import { Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

type ShortcutItem = {
  IconComponent: Icon;
  label: string;
  href: "/notes" | "/ideas" | "/reminders" | "/news" | "/brainstorm" | "/search" | "/settings";
};

const ITEMS: ShortcutItem[] = [
  { IconComponent: Note, label: "Notes", href: "/notes" },
  { IconComponent: Lightbulb, label: "Ideas", href: "/ideas" },
  { IconComponent: Alarm, label: "Reminders", href: "/reminders" },
  { IconComponent: Newspaper, label: "News", href: "/news" },
  { IconComponent: Brain, label: "Brainstorm", href: "/brainstorm" },
  { IconComponent: MagnifyingGlass, label: "Search", href: "/search" },
  { IconComponent: GearSix, label: "Settings", href: "/settings" },
];

const COLUMNS = 4;

export default function MoreScreen() {
  const theme = useTheme();
  const router = useRouter();

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScrollView contentContainerStyle={{ padding: theme.spacing[4], paddingTop: theme.spacing[5], gap: theme.spacing[4] }}>
        <Text variant="heading">More</Text>

        {/* Fixed-percentage columns (not %-width + parent gap, which
            overflows in RN) — the gutter comes from each tile's own
            padding, so 4 tiles always sum to exactly 100% regardless of
            screen width. Fixes the old row that silently assumed a
            width:"22%" + gap:10 combination would tile cleanly. */}
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {ITEMS.map((item, i) => (
            <View key={item.href} style={{ width: `${100 / COLUMNS}%`, padding: theme.spacing[1.5] }}>
              <AnimatedListItem index={i}>
                <ShortcutTile IconComponent={item.IconComponent} label={item.label} onPress={() => router.push(item.href)} />
              </AnimatedListItem>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
