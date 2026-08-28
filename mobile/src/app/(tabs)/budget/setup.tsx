import { useState } from "react";
import { useRouter } from "expo-router";
import { Plus, Trash, WarningCircle } from "phosphor-react-native";
import { ActivityIndicator, ScrollView, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { ScreenHeader } from "@/components/ScreenHeader";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { runSetup } from "@/features/budget/api";
import { parseIdr } from "@/features/budget/utils/parseIdr";
import { ApiError } from "@/api/client";
import { PressableScale } from "@/theme/motion";
import { Box, HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";

type WalletDraft = { name: string; openingBalanceText: string; isDefault: boolean };
type CategoryDraft = { name: string; kind: "fixed" | "variable"; monthlyLimitText: string };
type BillDraft = { name: string; amountText: string; dueDayText: string; categoryName: string };

let _id = 0;
const nextId = () => String(_id++);

export default function BudgetSetupScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { invalidate } = useBudgetRevision();

  const [payrollDayText, setPayrollDayText] = useState("25");
  const [wallets, setWallets] = useState<Record<string, WalletDraft>>({
    [nextId()]: { name: "Cash", openingBalanceText: "", isDefault: true },
  });
  const [categories, setCategories] = useState<Record<string, CategoryDraft>>({});
  const [bills, setBills] = useState<Record<string, BillDraft>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const walletEntries = Object.entries(wallets);
  const categoryEntries = Object.entries(categories);
  const billEntries = Object.entries(bills);

  const addWallet = () => setWallets((w) => ({ ...w, [nextId()]: { name: "", openingBalanceText: "", isDefault: false } }));
  const addCategory = () =>
    setCategories((c) => ({ ...c, [nextId()]: { name: "", kind: "variable", monthlyLimitText: "" } }));
  const addBill = () =>
    setBills((b) => ({ ...b, [nextId()]: { name: "", amountText: "", dueDayText: "", categoryName: "" } }));

  const setDefaultWallet = (id: string) =>
    setWallets((w) => Object.fromEntries(Object.entries(w).map(([k, v]) => [k, { ...v, isDefault: k === id }])));

  const canSave =
    walletEntries.length > 0 &&
    walletEntries.every(([, w]) => w.name.trim()) &&
    walletEntries.some(([, w]) => w.isDefault) &&
    categoryEntries.every(([, c]) => c.name.trim()) &&
    billEntries.every(([, b]) => b.name.trim() && parseIdr(b.amountText) !== null) &&
    !submitting;

  const handleSave = async () => {
    if (!canSave) return;
    setSubmitting(true);
    setError(null);
    try {
      await runSetup({
        payrollDay: parseInt(payrollDayText, 10) || 25,
        wallets: walletEntries.map(([, w]) => ({
          name: w.name.trim(),
          openingBalance: parseIdr(w.openingBalanceText) ?? 0,
          isDefault: w.isDefault,
          spendable: true,
        })),
        categories: categoryEntries.map(([, c]) => ({
          name: c.name.trim(),
          kind: c.kind,
          monthlyLimit: c.kind === "variable" ? parseIdr(c.monthlyLimitText) : null,
        })),
        bills: billEntries.map(([, b]) => ({
          name: b.name.trim(),
          amount: parseIdr(b.amountText) ?? 0,
          dueDay: b.dueDayText.trim() ? parseInt(b.dueDayText, 10) : null,
          categoryName: b.categoryName.trim() || undefined,
        })),
      });
      invalidate();
      router.replace("/budget");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't set up your budget — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Set up budget" />
      <ScrollView contentContainerStyle={{ padding: theme.spacing[4], gap: theme.spacing[4] }}>
        <Card>
          <Stack gap={2}>
            <Text variant="cardTitle">Pay cycle</Text>
            <Text variant="caption" tone="muted">
              What day of the month do you get paid?
            </Text>
            <FieldInput value={payrollDayText} onChangeText={setPayrollDayText} placeholder="25" keyboardType="number-pad" />
          </Stack>
        </Card>

        <Section
          title="Wallets"
          hint="Cash, bank accounts, e-wallets — anywhere money sits. One must be your default."
          onAdd={addWallet}
        >
          {walletEntries.map(([id, wallet]) => (
            <RowCard key={id} onRemove={walletEntries.length > 1 ? () => setWallets((w) => omit(w, id)) : undefined}>
              <FieldInput
                value={wallet.name}
                onChangeText={(name) => setWallets((w) => ({ ...w, [id]: { ...w[id], name } }))}
                placeholder="Name (e.g. Cash)"
              />
              <FieldInput
                value={wallet.openingBalanceText}
                onChangeText={(t) => setWallets((w) => ({ ...w, [id]: { ...w[id], openingBalanceText: t } }))}
                placeholder="Starting balance (e.g. 500rb)"
              />
              <PressableScale onPress={() => setDefaultWallet(id)} accessibilityRole="button" accessibilityLabel="Set as default wallet">
                <HStack align="center" gap={1.5}>
                  <Box
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: theme.radius.full,
                      borderWidth: 1,
                      borderColor: wallet.isDefault ? theme.colors.accent : theme.colors.divider,
                      backgroundColor: wallet.isDefault ? theme.colors.accent : "transparent",
                    }}
                  />
                  <Text variant="caption" tone={wallet.isDefault ? "accent" : "muted"}>
                    Default wallet
                  </Text>
                </HStack>
              </PressableScale>
            </RowCard>
          ))}
        </Section>

        <Section title="Categories" hint="Optional now — add spending categories with a monthly limit." onAdd={addCategory}>
          {categoryEntries.map(([id, category]) => (
            <RowCard key={id} onRemove={() => setCategories((c) => omit(c, id))}>
              <FieldInput
                value={category.name}
                onChangeText={(name) => setCategories((c) => ({ ...c, [id]: { ...c[id], name } }))}
                placeholder="Name (e.g. Fuel)"
              />
              <HStack gap={2}>
                <PressableScale
                  onPress={() => setCategories((c) => ({ ...c, [id]: { ...c[id], kind: "variable" } }))}
                  accessibilityRole="button"
                  accessibilityLabel="Variable category"
                  style={{ flex: 1 }}
                >
                  <KindPill label="Variable" selected={category.kind === "variable"} />
                </PressableScale>
                <PressableScale
                  onPress={() => setCategories((c) => ({ ...c, [id]: { ...c[id], kind: "fixed" } }))}
                  accessibilityRole="button"
                  accessibilityLabel="Fixed category"
                  style={{ flex: 1 }}
                >
                  <KindPill label="Fixed" selected={category.kind === "fixed"} />
                </PressableScale>
              </HStack>
              {category.kind === "variable" ? (
                <FieldInput
                  value={category.monthlyLimitText}
                  onChangeText={(t) => setCategories((c) => ({ ...c, [id]: { ...c[id], monthlyLimitText: t } }))}
                  placeholder="Monthly limit (e.g. 70rb)"
                />
              ) : null}
            </RowCard>
          ))}
        </Section>

        <Section title="Bills" hint="Optional now — recurring fixed expenses like rent or internet." onAdd={addBill}>
          {billEntries.map(([id, bill]) => (
            <RowCard key={id} onRemove={() => setBills((b) => omit(b, id))}>
              <FieldInput
                value={bill.name}
                onChangeText={(name) => setBills((b) => ({ ...b, [id]: { ...b[id], name } }))}
                placeholder="Name (e.g. House Rent)"
              />
              <FieldInput
                value={bill.amountText}
                onChangeText={(t) => setBills((b) => ({ ...b, [id]: { ...b[id], amountText: t } }))}
                placeholder="Amount (e.g. 955rb)"
              />
              <FieldInput
                value={bill.dueDayText}
                onChangeText={(t) => setBills((b) => ({ ...b, [id]: { ...b[id], dueDayText: t } }))}
                placeholder="Due day (optional, e.g. 25)"
                keyboardType="number-pad"
              />
            </RowCard>
          ))}
        </Section>

        {error ? (
          <HStack align="center" gap={2}>
            <WarningCircle size={16} color={theme.status.short} />
            <Text variant="label" tone="negative" style={{ flex: 1 }}>
              {error}
            </Text>
          </HStack>
        ) : null}

        <PressableScale onPress={handleSave} disabled={!canSave} accessibilityRole="button" accessibilityLabel="Save budget setup">
          <HStack
            align="center"
            justify="center"
            gap={1.5}
            py={3}
            radius="pill"
            bg={theme.colors.accent}
            style={{ opacity: canSave ? 1 : 0.5 }}
          >
            {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
            <Text variant="bodyStrong" style={{ color: theme.colors.bg }}>
              Save
            </Text>
          </HStack>
        </PressableScale>
      </ScrollView>
    </SafeAreaView>
  );
}

function omit<T extends Record<string, unknown>>(obj: T, key: string): T {
  const { [key]: _removed, ...rest } = obj;
  return rest as T;
}

function Section({
  title,
  hint,
  onAdd,
  children,
}: {
  title: string;
  hint: string;
  onAdd: () => void;
  children: React.ReactNode;
}) {
  const theme = useTheme();
  return (
    <Stack gap={3}>
      <HStack align="center" justify="space-between">
        <Stack gap={0.5} style={{ flex: 1 }}>
          <Text variant="cardTitle">{title}</Text>
          <Text variant="caption" tone="muted">
            {hint}
          </Text>
        </Stack>
        <PressableScale onPress={onAdd} accessibilityRole="button" accessibilityLabel={`Add ${title.toLowerCase()}`}>
          <Box p={2} radius="pill" bg={theme.colors.neutral[800]}>
            <Plus size={16} color={theme.colors.accent} weight="bold" />
          </Box>
        </PressableScale>
      </HStack>
      {children}
    </Stack>
  );
}

function RowCard({ children, onRemove }: { children: React.ReactNode; onRemove?: () => void }) {
  const theme = useTheme();
  return (
    <Card>
      <Stack gap={2}>
        {children}
        {onRemove ? (
          <PressableScale onPress={onRemove} accessibilityRole="button" accessibilityLabel="Remove">
            <HStack align="center" gap={1.5}>
              <Trash size={14} color={theme.status.short} />
              <Text variant="caption" tone="negative">
                Remove
              </Text>
            </HStack>
          </PressableScale>
        ) : null}
      </Stack>
    </Card>
  );
}

function FieldInput(props: {
  value: string;
  onChangeText: (t: string) => void;
  placeholder: string;
  keyboardType?: "default" | "number-pad" | "numbers-and-punctuation";
}) {
  const theme = useTheme();
  return (
    <Box p={3} radius="md" bg={theme.colors.bg} style={{ borderWidth: 1, borderColor: theme.colors.divider }}>
      <TextInput
        value={props.value}
        onChangeText={props.onChangeText}
        placeholder={props.placeholder}
        placeholderTextColor={theme.colors.neutral[500]}
        keyboardType={props.keyboardType ?? "default"}
        style={{ ...theme.type.body, color: theme.colors.text }}
        accessibilityLabel={props.placeholder}
      />
    </Box>
  );
}

function KindPill({ label, selected }: { label: string; selected: boolean }) {
  const theme = useTheme();
  return (
    <Box
      py={1.5}
      radius="pill"
      align="center"
      bg={selected ? theme.colors.accentRamp[900] : theme.colors.neutral[800]}
      style={{ borderWidth: 1, borderColor: selected ? theme.colors.accentRamp[700] : "transparent" }}
    >
      <Text variant="label" tone={selected ? "accent" : "secondary"}>
        {label}
      </Text>
    </Box>
  );
}
