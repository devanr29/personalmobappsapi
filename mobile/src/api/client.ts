import AsyncStorage from "@react-native-async-storage/async-storage";

import type { ApiEnvelope } from "./types";

// The URL baked in at build time (EXPO_PUBLIC_API_URL) — e.g. a deployed
// backend for a standalone build, or a laptop LAN IP for a dev client.
// Settings > API Server can override this per-install without a rebuild,
// which is what lets one installed app point at the cloud while you're
// out and at your laptop while you're actively coding against it.
export const DEFAULT_API_URL = process.env.EXPO_PUBLIC_API_URL ?? "";
const API_TOKEN = process.env.EXPO_PUBLIC_API_TOKEN ?? "";

export const API_URL_OVERRIDE_KEY = "nocturne.apiUrlOverride";

// AsyncStorage is async, but every request needs the base URL to build its
// fetch() call — resolving it once and caching in memory avoids awaiting
// storage on every single request. `undefined` means "not loaded yet".
let apiUrlOverride: string | null | undefined;
let apiUrlOverrideLoad: Promise<string | null> | null = null;

function loadApiUrlOverride(): Promise<string | null> {
  if (apiUrlOverride !== undefined) return Promise.resolve(apiUrlOverride);
  if (!apiUrlOverrideLoad) {
    apiUrlOverrideLoad = AsyncStorage.getItem(API_URL_OVERRIDE_KEY)
      .then((v) => (apiUrlOverride = v && v.trim() ? v.trim() : null))
      .catch(() => (apiUrlOverride = null));
  }
  return apiUrlOverrideLoad;
}

/** Current effective API base URL (override if set, else the build-time default). */
export async function getApiUrl(): Promise<string> {
  const override = await loadApiUrlOverride();
  return override ?? DEFAULT_API_URL;
}

/** Set (or, passing null/empty, clear) the per-install API URL override. */
export async function setApiUrlOverride(url: string | null): Promise<void> {
  const trimmed = url && url.trim() ? url.trim() : null;
  apiUrlOverride = trimmed;
  try {
    if (trimmed) await AsyncStorage.setItem(API_URL_OVERRIDE_KEY, trimmed);
    else await AsyncStorage.removeItem(API_URL_OVERRIDE_KEY);
  } catch {
    // Best-effort persistence — the in-memory override still applies for
    // the rest of this session even if storage itself is unavailable.
  }
}

// Home/Budget/Calendar were observed spinning on the skeleton forever on
// a physical device with no error, no retry, nothing — the underlying
// request had no timeout, so a slow or dropped connection just hung.
// fetch() has no native timeout; AbortController is the standard way to
// bound it. 20s is above this app's worst realistic response (the
// aggregate /api/home read) but still short enough that "stuck loading"
// resolves into a visible, retryable error instead of an eternal spinner.
const REQUEST_TIMEOUT_MS = 20_000;

// Wallet sync POSTs are the one exception: each call is server-bounded to a
// short work budget but a single page of records against a far-region DB
// can still take a while, and the server persists its resume offset either
// way — so a longer ceiling here just lets that one call finish and report
// progress instead of aborting into a 499.
export const LONG_REQUEST_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function requestFull<T, M = Record<string, never>>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<{ data: T; meta: M }> {
  const { timeoutMs, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs ?? REQUEST_TIMEOUT_MS);

  let res: Response;
  try {
    const base = await getApiUrl();
    res = await fetch(`${base}${path}`, {
      ...fetchOptions,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${API_TOKEN}`,
        ...fetchOptions.headers,
      },
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("TIMEOUT", `Request to ${path} took too long. Check your connection and try again.`, 0);
    }
    throw new ApiError("NETWORK_ERROR", "Couldn't reach the server. Check your connection.", 0);
  } finally {
    clearTimeout(timeout);
  }

  let body: ApiEnvelope<T> & { meta: M };
  try {
    body = await res.json();
  } catch {
    throw new ApiError("INVALID_RESPONSE", "Server response was not valid JSON.", res.status);
  }

  if ("error" in body) {
    throw new ApiError(body.error.code, body.error.message, res.status);
  }
  return body;
}

async function request<T>(path: string, options: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const body = await requestFull<T>(path, options);
  return body.data;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  // Same as get, but also surfaces the envelope's meta — needed by
  // list endpoints like /budget/transactions that paginate via meta
  // (total/limit/offset/hasMore) rather than in the data payload.
  getFull: <T, M = Record<string, never>>(path: string) => requestFull<T, M>(path, { method: "GET" }),
  post: <T>(path: string, payload?: unknown, opts?: { timeoutMs?: number }) =>
    request<T>(path, {
      method: "POST",
      body: payload !== undefined ? JSON.stringify(payload) : undefined,
      timeoutMs: opts?.timeoutMs,
    }),
  patch: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: "PATCH", body: payload !== undefined ? JSON.stringify(payload) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
