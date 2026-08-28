import { Box, Text, type Tone } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export type TagVariant = "solid" | "accent" | "outline";

export type TagProps = {
  label: string;
  variant?: TagVariant;
};

export function Tag({ label, variant = "solid" }: TagProps) {
  const theme = useTheme();

  const variants: Record<TagVariant, { bg: string; borderColor?: string; tone: Tone }> = {
    solid: { bg: theme.colors.neutral[800], tone: "secondary" },
    accent: { bg: theme.colors.accentRamp[900], borderColor: theme.colors.accentRamp[800], tone: "accent" },
    outline: { bg: "transparent", borderColor: theme.colors.neutral[700], tone: "secondary" },
  };
  const variantStyle = variants[variant];

  return (
    <Box
      py={1}
      px={2}
      radius="md"
      bg={variantStyle.bg}
      style={{
        alignSelf: "flex-start",
        borderWidth: variantStyle.borderColor ? 1 : 0,
        borderColor: variantStyle.borderColor,
      }}
    >
      <Text variant="caption" tone={variantStyle.tone} style={{ fontFamily: theme.fontFamily.medium }}>
        {label}
      </Text>
    </Box>
  );
}
