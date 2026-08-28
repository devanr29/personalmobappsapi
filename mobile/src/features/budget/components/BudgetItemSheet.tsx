import { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import { Trash } from "phosphor-react-native";

import { GlassSurface } from "@/components/GlassSurface";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { ApiError } from "@/api/client";
import { createBill, createCategory, deleteBill, deleteCategory, updateBill, updateCategory } from "../api";
import type { Bill, Category } from "../types";
import { parseIdr } from "../utils/parseIdr";
import { AmountField } from "./AmountField";

export type BudgetItemSheetProps = {
  visible: boolean;
  onClose: () => void;
  /** Fired after any successful create/update/delete — caller invalidates
   * the budget revision so every screen showing the daily budget (which
   * these limits feed directly) refetches with the new numbers. */
  onSaved: () => void;
  itemKind: "category" | "bill";
  /** Present -> editing that row (PATCH/DELETE). Absent -> creating. */
  editing?: Category | Bill | null;
};

/** Create/edit sheet shared by the Fixed budget (bills) and Variable budget
 * (kind='variable' categories) sections on the Budget overview screen. Two
 * item kinds share this one sheet rather than forking into
 * CategorySheet/BillSheet, since the fields mostly overlap (name + a money
 * amount) and the save/delete/error plumbing would otherwise be duplicated
 * verbatim — see TransactionSheet.tsx for the same create-or-edit-by-prop
 * pattern this one follows. */
export function BudgetItemSheet({ visible, onClose, onSaved, itemKind, editing }: BudgetItemSheetProps) {
  const theme = useTheme();
  const isEditing = !!editing;
  const isBill = itemKind === "bill";

  const [name, setName] = useState("");
  const [amountText, setAmountText] = useState("");
  const [dueDayText, setDueDayText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Same render-phase reset-on-open pattern as TransactionSheet — keyed on
  // *which* row is open so switching from editing one item to another (or
  // to a fresh create) re-seeds the fields without an extra render.
  const sessionKey = visible ? (editing ? `edit-${itemKind}-${editing.id}` : `create-${itemKind}`) : null;
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (sessionKey !== null && openFor !== sessionKey) {
    setOpenFor(sessionKey);
    setError(null);
    if (editing) {
      setName(editing.name);
      setAmountText(isBill ? String((editing as Bill).amount) : String((editing as Category).monthlyLimit ?? ""));
      setDueDayText(isBill && (editing as Bill).dueDay != null ? String((editing as Bill).dueDay) : "");
    } else {
      setName("");
      setAmountText("");
      setDueDayText("");
    }
  }

  const handleClose = () => {
    if (submitting) return;
    onClose();
  };

  const parsedAmount = parseIdr(amountText);
  // Variable categories also require a positive limit — the daily-budget
  // math treats a missing monthlyLimit as a budget of 0 (service.py:
  // `c["monthly_limit"] or 0`), which would make any spend on a "capless"
  // category show as immediately over budget rather than untracked.
  const amountValid = parsedAmount !== null && parsedAmount > 0;
  const canSave = name.trim().length > 0 && amountValid && !submitting;

  const handleSave = async () => {
    if (!canSave) return;
    setSubmitting(true);
    setError(null);
    try {
      const dueDay = dueDayText.trim() ? parseInt(dueDayText, 10) : null;
      if (isBill) {
        if (isEditing) {
          await updateBill(editing!.id, { name: name.trim(), amount: parsedAmount ?? 0, dueDay });
        } else {
          await createBill({ name: name.trim(), amount: parsedAmount ?? 0, dueDay });
        }
      } else {
        if (isEditing) {
          await updateCategory(editing!.id, { name: name.trim(), monthlyLimit: parsedAmount });
        } else {
          await createCategory({ name: name.trim(), kind: "variable", monthlyLimit: parsedAmount });
        }
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!editing || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (isBill) {
        await deleteBill(editing.id);
      } else {
        await deleteCategory(editing.id);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete — it may still have transactions attached.");
      setSubmitting(false);
    }
  };

  const title = isBill
    ? isEditing
      ? "Edit fixed budget"
      : "Add fixed budget"
    : isEditing
      ? "Edit variable budget"
      : "Add variable budget";

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={handleClose}>
      {/* KeyboardAvoidingView must own the full-screen flex box (not sit
       * inside it) so its height/padding response to the keyboard actually
       * reflows the flex-end backdrop below it — nested the other way
       * round, the backdrop's own flex-end just re-anchors to the same
       * screen bottom and the sheet stays pinned behind the keyboard
       * instead of floating up to follow it. */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
          <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
            <ScrollView keyboardShouldPersistTaps="handled">
              <Stack p={4} gap={4}>
                <Text variant="heading">{title}</Text>

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    Name
                  </Text>
                  <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
                    <TextInput
                      value={name}
                      onChangeText={setName}
                      placeholder={isBill ? "e.g. House Rent" : "e.g. Groceries"}
                      placeholderTextColor={theme.colors.neutral[500]}
                      style={{ ...theme.type.body, color: theme.colors.text }}
                      editable={!submitting}
                      accessibilityLabel="Name"
                    />
                  </Box>
                </Stack>

                <Stack gap={1.5}>
                  <Text variant="caption" tone="muted">
                    {isBill ? "Amount" : "Monthly limit"}
                  </Text>
                  <AmountField rawText={amountText} onChangeRawText={setAmountText} />
                </Stack>

                {isBill ? (
                  <Stack gap={1.5}>
                    <Text variant="caption" tone="muted">
                      Due day (optional)
                    </Text>
                    <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
                      <TextInput
                        value={dueDayText}
                        onChangeText={setDueDayText}
                        placeholder="e.g. 25"
                        placeholderTextColor={theme.colors.neutral[500]}
                        keyboardType="number-pad"
                        style={{ ...theme.type.body, color: theme.colors.text }}
                        editable={!submitting}
                        accessibilityLabel="Due day"
                      />
                    </Box>
                  </Stack>
                ) : null}

                {error ? (
                  <Text variant="label" tone="negative">
                    {error}
                  </Text>
                ) : null}

                <HStack align="center" justify="space-between">
                  {isEditing ? (
                    <Pressable onPress={handleDelete} disabled={submitting} accessibilityRole="button" accessibilityLabel="Delete">
                      <HStack align="center" gap={1.5} py={2}>
                        <Trash size={14} color={theme.status.short} />
                        <Text variant="label" tone="negative">
                          Delete
                        </Text>
                      </HStack>
                    </Pressable>
                  ) : (
                    <Box />
                  )}
                  <HStack justify="flex-end" gap={3}>
                    <Pressable onPress={handleClose} disabled={submitting} accessibilityRole="button" accessibilityLabel="Cancel">
                      <Box py={2} px={4}>
                        <Text variant="label" tone="muted">
                          Cancel
                        </Text>
                      </Box>
                    </Pressable>
                    <Pressable onPress={handleSave} disabled={!canSave} accessibilityRole="button" accessibilityLabel="Save">
                      <HStack
                        align="center"
                        gap={1.5}
                        py={2}
                        px={4}
                        radius="pill"
                        bg={theme.colors.accent}
                        style={{ opacity: canSave ? 1 : 0.5 }}
                      >
                        {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
                        <Text variant="label" style={{ color: theme.colors.bg }}>
                          Save
                        </Text>
                      </HStack>
                    </Pressable>
                  </HStack>
                </HStack>
              </Stack>
            </ScrollView>
          </GlassSurface>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
