import { Skeleton } from "./Skeleton";
import { HStack, Stack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export function HomeSkeleton() {
  const theme = useTheme();

  return (
    <Stack gap={4}>
      <Skeleton height={62} radius={theme.radius.md} />
      <Skeleton height={45} radius={theme.radius.lg} />
      <HStack gap={3}>
        <Skeleton height={80} radius={theme.radius.md} />
        <Skeleton height={80} radius={theme.radius.md} />
      </HStack>
      <Skeleton height={110} radius={theme.radius.md} />
      <Skeleton height={130} radius={theme.radius.md} />
      <Skeleton height={58} radius={theme.radius.md} />
      <Skeleton height={100} radius={theme.radius.md} />
      <HStack gap={3}>
        <Skeleton height={64} radius={theme.radius.md} />
        <Skeleton height={64} radius={theme.radius.md} />
        <Skeleton height={64} radius={theme.radius.md} />
        <Skeleton height={64} radius={theme.radius.md} />
      </HStack>
    </Stack>
  );
}
