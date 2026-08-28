import { TextInput } from "react-native";

import { Box, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";
import { parseIdr } from "../utils/parseIdr";

export type AmountFieldProps = {
  /** Raw text the user is typing — e.g. "50rb". Kept separate from the
   * parsed integer so the field never fights the user mid-edit (typing
   * "50" then "rb" would otherwise get reformatted after every keystroke). */
  rawText: string;
  onChangeRawText: (text: string) => void;
  autoFocus?: boolean;
  /** Smaller type sized for inline use inside a card row instead of a
   * full-screen sheet. */
  compact?: boolean;
};

/** Free-text IDR entry ("50rb", "1,5jt", "50.000", "45000") with a live
 * parsed-amount preview underneath, via the same parseIdr rules quick-add
 * uses server-side. */
export function AmountField({ rawText, onChangeRawText, autoFocus, compact }: AmountFieldProps) {
  const theme = useTheme();
  const parsed = parseIdr(rawText);

  return (
    <Stack gap={1.5}>
      <Box
        p={compact ? 2 : 3}
        radius="md"
        bg={theme.colors.bg}
        style={{ borderWidth: 1, borderColor: theme.colors.divider }}
      >
        <TextInput
          value={rawText}
          onChangeText={onChangeRawText}
          placeholder="e.g. 50rb"
          placeholderTextColor={theme.colors.neutral[500]}
          keyboardType="numbers-and-punctuation"
          autoFocus={autoFocus}
          style={{ ...(compact ? theme.type.body : theme.type.title), color: theme.colors.text }}
          accessibilityLabel="Amount"
        />
      </Box>
      <Text variant="caption" tone={parsed === null ? "faint" : "muted"} numeric>
        {parsed === null ? "Enter an amount" : formatRupiah(parsed)}
      </Text>
    </Stack>
  );
}
