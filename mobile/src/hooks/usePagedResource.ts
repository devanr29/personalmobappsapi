import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";

export type PagedFetcher<T> = (offset: number) => Promise<{ items: T[]; total: number; hasMore: boolean }>;

export type UsePagedResourceResult<T> = {
  items: T[];
  total: number;
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  /** Resets to page 0 and refetches from scratch. */
  refetch: () => void;
  /** Appends the next page. No-op while already loading or when hasMore is false. */
  loadMore: () => void;
  mutateItems: (apply: (prev: T[]) => T[], rollback: (prev: T[]) => T[], action: () => Promise<unknown>) => void;
};

/**
 * Sibling to useResource for paginated lists. useResource replaces `data`
 * wholesale on every load(), which is right for the ~10 non-paginated
 * screens using it — adding page-accumulation there would be the wrong
 * generalization. This hook exists for the one screen that needs it.
 *
 * Contract: on screen focus or a `revision` change, the accumulated pages
 * are DISCARDED and refetch starts over from page 0. Otherwise a user who
 * scrolled to row 400 would refetch 400 rows on every tab switch — the
 * exact pathology this app's focus-refetch model invites if unguarded.
 * Scroll position resetting on tab-away is the accepted trade-off,
 * consistent with every other screen in the app.
 */
export function usePagedResource<T>(
  fetchPage: PagedFetcher<T>,
  errorMessage = "Couldn't load data.",
  revision?: number,
): UsePagedResourceResult<T> {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadedOnce = useRef(false);
  const lastRevision = useRef(revision);
  // Tracks how many rows are already loaded so loadMore() always requests
  // the next unseen page, even mid-flight — reading it from a ref (not
  // items.length in a closure) avoids a stale offset on a fast double-tap.
  const offsetRef = useRef(0);
  const loadingMoreRef = useRef(false);

  const loadFirstPage = useCallback(async () => {
    if (!loadedOnce.current) setLoading(true);
    setError(null);
    try {
      const page = await fetchPage(0);
      setItems(page.items);
      setTotal(page.total);
      setHasMore(page.hasMore);
      offsetRef.current = page.items.length;
      loadedOnce.current = true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : errorMessage);
    } finally {
      setLoading(false);
    }
  }, [fetchPage, errorMessage]);

  useFocusEffect(
    useCallback(() => {
      loadFirstPage();
    }, [loadFirstPage]),
  );

  const loadMore = useCallback(() => {
    if (loadingMoreRef.current || !hasMore) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    fetchPage(offsetRef.current)
      .then((page) => {
        setItems((prev) => [...prev, ...page.items]);
        setTotal(page.total);
        setHasMore(page.hasMore);
        offsetRef.current += page.items.length;
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : errorMessage);
      })
      .finally(() => {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      });
  }, [fetchPage, hasMore, errorMessage]);

  const mutateItems = useCallback(
    (apply: (prev: T[]) => T[], rollback: (prev: T[]) => T[], action: () => Promise<unknown>) => {
      setItems((prev) => apply(prev));
      action().catch(() => {
        setItems((prev) => rollback(prev));
      });
    },
    [],
  );

  // Cross-screen invalidation, mirroring useResource.ts exactly: a focus
  // event already refetches on its own, this covers a revision bump while
  // this screen stays mounted-but-focused. load() is async and only
  // touches state from its own .then/catch, so this doesn't trip the
  // synchronous-setState-in-effect lint rule.
  useEffect(() => {
    if (revision === undefined || revision === lastRevision.current) return;
    lastRevision.current = revision;
    loadFirstPage();
  }, [revision, loadFirstPage]);

  return { items, total, hasMore, loading, loadingMore, error, refetch: loadFirstPage, loadMore, mutateItems };
}
