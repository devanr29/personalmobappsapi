import { useCallback, useEffect, useState } from "react";
import { PiggyBank, Plus } from "phosphor-react-native";
import { ActivityIndicator, Modal, Pressable, ScrollView, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FAB } from "@/components/FAB";
import { GlassSurface } from "@/components/GlassSurface";
import { ScreenHeader } from "@/components/ScreenHeader";
import { Skeleton } from "@/components/Skeleton";
import { Meter, clamp01 } from "@/components/charts";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { contributeToGoal, createGoal, listGoals, listWallets } from "@/features/budget/api";
import type { Goal, Wallet } from "@/features/budget/types";
import { parseIdr } from "@/features/budget/utils/parseIdr";
import { ApiError } from "@/api/client";
import { useResource } from "@/hooks/useResource";
import { PressableScale } from "@/theme/motion";
import { HStack, Stack, Text } from "@/theme/primitives";
import { useTheme } from "@/theme/ThemeProvider";
import { formatRupiah } from "@/utils/currency";

export default function BudgetGoalsScreen() {
  const theme = useTheme();
  const { revision, invalidate } = useBudgetRevision();
  const [createVisible, setCreateVisible] = useState(false);
  const [contributingGoal, setContributingGoal] = useState<Goal | null>(null);

  const fetcher = useCallback(() => listGoals(), []);
  const { data: goals, loading, error, refetch } = useResource<Goal[]>(fetcher, "Couldn't load goals.", revision);

  const handleChanged = () => {
    invalidate();
    refetch();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.bg }} edges={["top"]}>
      <ScreenHeader title="Goals" />

      {loading ? (
        <Stack p={4} gap={3}>
          <Skeleton height={100} radius={theme.radius.md} />
          <Skeleton height={100} radius={theme.radius.md} />
        </Stack>
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !goals || goals.length === 0 ? (
        <EmptyState message="No savings goals yet. Tap + to start one." IconComponent={PiggyBank} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: theme.spacing[4], gap: theme.spacing[3] }}>
          {goals.map((g) => (
            <GoalCard key={g.id} goal={g} onContribute={() => setContributingGoal(g)} />
          ))}
        </ScrollView>
      )}

      <FAB IconComponent={Plus} onPress={() => setCreateVisible(true)} accessibilityLabel="Add goal" />
      <CreateGoalSheet visible={createVisible} onClose={() => setCreateVisible(false)} onSaved={handleChanged} />
      <ContributeSheet goal={contributingGoal} onClose={() => setContributingGoal(null)} onSaved={handleChanged} />
    </SafeAreaView>
  );
}

function GoalCard({ goal, onContribute }: { goal: Goal; onContribute: () => void }) {
  const theme = useTheme();
  const progress = goal.targetAmount > 0 ? clamp01(goal.saved / goal.targetAmount) : 0;
  const isDone = goal.saved >= goal.targetAmount;

  return (
    <Card>
      <Stack gap={3}>
        <HStack align="center" justify="space-between">
          <Text variant="cardTitle">{goal.name}</Text>
          {isDone ? (
            <Text variant="caption" tone="positive">
              Reached
            </Text>
          ) : null}
        </HStack>
        <Meter value={progress} color={isDone ? theme.status.comfortable : theme.colors.accent} />
        <HStack justify="space-between">
          <Text variant="caption" tone="muted" numeric>
            {formatRupiah(goal.saved)} saved
          </Text>
          <Text variant="caption" tone="muted" numeric>
            of {formatRupiah(goal.targetAmount)}
          </Text>
        </HStack>
        {goal.monthlyContribution ? (
          <Text variant="caption" tone="faint">
            {formatRupiah(goal.monthlyContribution)}/period reserved from free money
          </Text>
        ) : null}
        <PressableScale onPress={onContribute} accessibilityRole="button" accessibilityLabel={`Contribute to ${goal.name}`}>
          <Stack py={2} radius="pill" bg={theme.colors.neutral[800]} align="center">
            <Text variant="label" tone="accent">
              Contribute
            </Text>
          </Stack>
        </PressableScale>
      </Stack>
    </Card>
  );
}

function CreateGoalSheet({ visible, onClose, onSaved }: { visible: boolean; onClose: () => void; onSaved: () => void }) {
  const theme = useTheme();
  const [name, setName] = useState("");
  const [targetText, setTargetText] = useState("");
  const [monthlyText, setMonthlyText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [openFor, setOpenFor] = useState(false);
  if (visible !== openFor) {
    setOpenFor(visible);
    if (visible) {
      setName("");
      setTargetText("");
      setMonthlyText("");
      setError(null);
    }
  }

  const target = parseIdr(targetText);
  const canSave = name.trim().length > 0 && target !== null && target > 0 && !submitting;

  const handleSave = async () => {
    if (!canSave || target === null) return;
    setSubmitting(true);
    setError(null);
    try {
      const monthly = parseIdr(monthlyText);
      await createGoal({ name: name.trim(), targetAmount: target, monthlyContribution: monthly ?? undefined });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the goal — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={submitting ? undefined : onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
          <Stack p={4} gap={4}>
            <Text variant="heading">New goal</Text>
            <FormField value={name} onChangeText={setName} placeholder="Name (e.g. Emergency fund)" />
            <FormField value={targetText} onChangeText={setTargetText} placeholder="Target amount (e.g. 5jt)" />
            <FormField value={monthlyText} onChangeText={setMonthlyText} placeholder="Reserve per period, optional (e.g. 200rb)" />
            {error ? (
              <Text variant="label" tone="negative">
                {error}
              </Text>
            ) : null}
            <HStack justify="flex-end" gap={3}>
              <Pressable onPress={onClose} disabled={submitting} accessibilityRole="button" accessibilityLabel="Cancel">
                <Stack py={2} px={4}>
                  <Text variant="label" tone="muted">
                    Cancel
                  </Text>
                </Stack>
              </Pressable>
              <Pressable onPress={handleSave} disabled={!canSave} accessibilityRole="button" accessibilityLabel="Save">
                <HStack align="center" gap={1.5} py={2} px={4} radius="pill" bg={theme.colors.accent} style={{ opacity: canSave ? 1 : 0.5 }}>
                  {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
                  <Text variant="label" style={{ color: theme.colors.bg }}>
                    Save
                  </Text>
                </HStack>
              </Pressable>
            </HStack>
          </Stack>
        </GlassSurface>
      </View>
    </Modal>
  );
}

function ContributeSheet({ goal, onClose, onSaved }: { goal: Goal | null; onClose: () => void; onSaved: () => void }) {
  const theme = useTheme();
  const [amountText, setAmountText] = useState("");
  const [walletId, setWalletId] = useState<number | null>(null);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!goal) return;
    listWallets().then(setWallets).catch(() => {});
  }, [goal]);

  const [openForId, setOpenForId] = useState<number | null>(null);
  if ((goal?.id ?? null) !== openForId) {
    setOpenForId(goal?.id ?? null);
    setAmountText("");
    setWalletId(null);
    setError(null);
  }

  const amount = parseIdr(amountText);
  const canSave = amount !== null && amount > 0 && !submitting;

  const handleSave = async () => {
    if (!goal || !canSave || amount === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await contributeToGoal(goal.id, amount, walletId ?? undefined);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the contribution — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={!!goal} animationType="slide" transparent onRequestClose={submitting ? undefined : onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" }}>
        <GlassSurface style={{ borderTopLeftRadius: theme.radius.lg, borderTopRightRadius: theme.radius.lg }}>
          <Stack p={4} gap={4}>
            <Text variant="heading">Contribute to {goal?.name}</Text>
            <FormField value={amountText} onChangeText={setAmountText} placeholder="Amount (e.g. 200rb)" />
            {wallets.length > 0 ? (
              <Stack gap={1.5}>
                <Text variant="caption" tone="muted">
                  From wallet
                </Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  <HStack gap={2}>
                    {wallets.map((w) => (
                      <Pressable key={w.id} onPress={() => setWalletId(w.id)} accessibilityRole="button" accessibilityLabel={w.name}>
                        <Stack
                          py={1.5}
                          px={3}
                          radius="pill"
                          bg={walletId === w.id ? theme.colors.accentRamp[900] : theme.colors.neutral[800]}
                        >
                          <Text variant="label" tone={walletId === w.id ? "accent" : "secondary"}>
                            {w.name}
                          </Text>
                        </Stack>
                      </Pressable>
                    ))}
                  </HStack>
                </ScrollView>
              </Stack>
            ) : null}
            {error ? (
              <Text variant="label" tone="negative">
                {error}
              </Text>
            ) : null}
            <HStack justify="flex-end" gap={3}>
              <Pressable onPress={onClose} disabled={submitting} accessibilityRole="button" accessibilityLabel="Cancel">
                <Stack py={2} px={4}>
                  <Text variant="label" tone="muted">
                    Cancel
                  </Text>
                </Stack>
              </Pressable>
              <Pressable onPress={handleSave} disabled={!canSave} accessibilityRole="button" accessibilityLabel="Save">
                <HStack align="center" gap={1.5} py={2} px={4} radius="pill" bg={theme.colors.accent} style={{ opacity: canSave ? 1 : 0.5 }}>
                  {submitting ? <ActivityIndicator size="small" color={theme.colors.bg} /> : null}
                  <Text variant="label" style={{ color: theme.colors.bg }}>
                    Save
                  </Text>
                </HStack>
              </Pressable>
            </HStack>
          </Stack>
        </GlassSurface>
      </View>
    </Modal>
  );
}

function FormField({ value, onChangeText, placeholder }: { value: string; onChangeText: (t: string) => void; placeholder: string }) {
  const theme = useTheme();
  return (
    <View
      style={{
        padding: theme.spacing[3],
        borderRadius: theme.radius.md,
        backgroundColor: theme.colors.bg,
        borderWidth: 1,
        borderColor: theme.colors.divider,
      }}
    >
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={theme.colors.neutral[500]}
        style={{ ...theme.type.body, color: theme.colors.text }}
        accessibilityLabel={placeholder}
      />
    </View>
  );
}
