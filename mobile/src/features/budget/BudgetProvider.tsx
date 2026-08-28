// Mounted in the root layout (alongside SettingsProvider) rather than
// inside the budget tab, because BudgetCard renders on Home — outside the
// budget tab entirely. `revision` lets useResource (see the `revision` param
// added there) refetch screens that show budget data but didn't perform the
// mutation themselves, on top of the in-band {transaction, summary} response
// every mutating budget endpoint already returns for the acting screen.
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export interface BudgetContextValue {
  revision: number;
  invalidate: () => void;
}

const BudgetContext = createContext<BudgetContextValue>({ revision: 0, invalidate: () => {} });

export function BudgetProvider({ children }: { children: ReactNode }) {
  const [revision, setRevision] = useState(0);
  const value = useMemo(() => ({ revision, invalidate: () => setRevision((r) => r + 1) }), [revision]);
  return <BudgetContext.Provider value={value}>{children}</BudgetContext.Provider>;
}

export function useBudgetRevision(): BudgetContextValue {
  return useContext(BudgetContext);
}
