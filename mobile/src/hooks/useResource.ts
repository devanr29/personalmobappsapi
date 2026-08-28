import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";

export type UseResourceResult<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /**
   * Applies `apply` to the local state immediately, runs `action`, and — if
   * it rejects — replaces the local state with `rollback` applied to
   * whatever is current at that point (not a stale snapshot from before
   * the optimistic update).
   */
  mutate: (apply: (prev: T) => T, rollback: (prev: T) => T, action: () => Promise<unknown>) => void;
};

export function useResource<T>(
  fetcher: () => Promise<T>,
  errorMessage = "Couldn't load data.",
  revision?: number,
): UseResourceResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadedOnce = useRef(false);
  const lastRevision = useRef(revision);

  const load = useCallback(async () => {
    if (!loadedOnce.current) setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
      loadedOnce.current = true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : errorMessage);
    } finally {
      setLoading(false);
    }
  }, [fetcher, errorMessage]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  // Cross-screen invalidation (e.g. Home's BudgetCard after a mutation made
  // from the Budget tab) — a focus event already refetches on its own, this
  // just covers screens that stay mounted-but-focused across the change.
  useEffect(() => {
    if (revision === undefined || revision === lastRevision.current) return;
    lastRevision.current = revision;
    load();
  }, [revision, load]);

  const mutate = useCallback(
    (apply: (prev: T) => T, rollback: (prev: T) => T, action: () => Promise<unknown>) => {
      setData((prev) => (prev !== null ? apply(prev) : prev));
      action().catch(() => {
        setData((prev) => (prev !== null ? rollback(prev) : prev));
      });
    },
    [],
  );

  return { data, loading, error, refetch: load, mutate };
}
