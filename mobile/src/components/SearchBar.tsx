import { MagnifyingGlass } from "phosphor-react-native";
import { TextInput } from "react-native";

import { HStack } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

export interface SearchBarProps {
  value: string;
  onChangeText: (text: string) => void;
  onSubmit: () => void;
  placeholder: string;
}

export function SearchBar({ value, onChangeText, onSubmit, placeholder }: SearchBarProps) {
  const theme = useTheme();

  return (
    <HStack align="center" gap={2} py={2} px={4} radius="pill" bg={theme.colors.surface}>
      <MagnifyingGlass size={16} color={theme.colors.neutral[500]} />
      <TextInput
        value={value}
        onChangeText={onChangeText}
        onSubmitEditing={onSubmit}
        placeholder={placeholder}
        placeholderTextColor={theme.colors.neutral[500]}
        style={{ flex: 1, ...theme.type.body, color: theme.colors.text, padding: theme.spacing[0] }}
        returnKeyType="search"
      />
    </HStack>
  );
}
