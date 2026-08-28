import { useCallback } from "react";

import { getHome } from "@/api/home";
import { completeTask } from "@/api/tasks";
import type { HomeResponse, Task } from "@/api/types";
import { useBudgetRevision } from "@/features/budget/BudgetProvider";
import { useResource } from "@/hooks/useResource";

export type UseHomeResult = {
  data: HomeResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  completeTaskOptimistic: (id: string) => void;
};

export function useHome(): UseHomeResult {
  const { revision } = useBudgetRevision();
  const { data, loading, error, refetch, mutate } = useResource<HomeResponse>(
    getHome,
    "Couldn't load your home screen.",
    revision,
  );

  const completeTaskOptimistic = useCallback(
    (id: string) => {
      const setStatus = (status: Task["status"]) => (prev: HomeResponse) => ({
        ...prev,
        tasks: prev.tasks.map((t) => (t.id === id ? { ...t, status } : t)),
      });

      mutate(setStatus("completed"), setStatus("needsAction"), () => completeTask(id));
    },
    [mutate],
  );

  return { data, loading, error, refetch, completeTaskOptimistic };
}
