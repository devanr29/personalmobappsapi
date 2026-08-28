import type { ReactNode } from "react";
import { Pressable } from "react-native";
import Swipeable from "react-native-gesture-handler/ReanimatedSwipeable";

import { Box, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type SwipeableRowProps = {
  children: ReactNode;
  onDelete: () => void;
};

export function SwipeableRow({ children, onDelete }: SwipeableRowProps) {
  const theme = useTheme();

  return (
    <Swipeable
      rightThreshold={40}
      renderRightActions={(_progress, _translation, swipeableMethods) => (
        <Pressable
          onPress={() => {
            swipeableMethods.close();
            onDelete();
          }}
          accessibilityRole="button"
          accessibilityLabel="Delete"
        >
          <Box
            radius="md"
            bg={theme.colors.negative}
            align="center"
            justify="center"
            style={{ width: 72, marginLeft: theme.spacing[2], height: "100%" }}
          >
            <Text variant="label" style={{ color: theme.colors.bg, fontFamily: theme.fontFamily.medium }}>
              Delete
            </Text>
          </Box>
        </Pressable>
      )}
    >
      {children}
    </Swipeable>
  );
}
