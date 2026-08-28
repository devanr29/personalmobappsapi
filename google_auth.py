import os
import json
import threading
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from config import SCOPES
from tracer import trace, logger
import pickle

_google_services_cache = None
# GET /api/home calls this from two concurrent worker threads (Calendar +
# Tasks) via ThreadPoolExecutor -- without a lock, both could see the cache
# empty on the very first request, race to build services, and race to
# refresh the same OAuth token concurrently (wasteful at best; some OAuth
# providers invalidate a refresh token once used, which would make a
# concurrent second refresh with the now-stale token fail outright).
_google_services_lock = threading.Lock()

# bot_state key the refreshed token is persisted under — see
# _load_persisted_token/_persist_token below.
_TOKEN_STATE_KEY = "google_oauth_token_json"


def _load_persisted_token():
    """Best-effort load of a previously-refreshed token from bot_state
    (Postgres/Neon). On a host with an ephemeral filesystem (Render,
    Cloud Run) token.pickle does not survive a redeploy or cold start, but
    bot_state does — this is what lets a refreshed token stick instead of
    every cold start falling back to whatever was baked into
    GOOGLE_TOKEN_B64 at deploy time. Stored as the credentials' own JSON
    form (Credentials.to_json()), not pickle — this is data our own
    refresh step wrote, so JSON is the simpler and equally sufficient
    format, with no deserialization surface to worry about."""
    try:
        from database import state_get  # deferred: avoids a hard import-time
        # dependency on the DB layer for callers that never touch Google auth
        raw = state_get(_TOKEN_STATE_KEY)
    except Exception as e:
        logger.warning(f"[Google Auth] Could not read persisted token from bot_state: {e}")
        return None
    if not raw:
        return None
    try:
        return Credentials.from_authorized_user_info(json.loads(raw), scopes=SCOPES)
    except Exception as e:
        logger.warning(f"[Google Auth] Failed to decode persisted token from bot_state: {e}")
        return None


def _persist_token(creds):
    """Save the just-refreshed token to bot_state so the next cold start
    picks it up instead of a stale GOOGLE_TOKEN_B64."""
    try:
        from database import state_set
        state_set(_TOKEN_STATE_KEY, creds.to_json())
    except Exception as e:
        logger.warning(f"[Google Auth] Failed to persist refreshed token to bot_state: {e}")


def get_google_services():
    """Return (calendar, sheets, tasks) services. Loads once and caches.
    Reads token from GOOGLE_TOKEN_B64 env var (base64) or token.pickle file.
    Raises RuntimeError if no valid credentials are available."""
    global _google_services_cache
    if _google_services_cache is not None:
        return _google_services_cache

    with _google_services_lock:
        if _google_services_cache is not None:
            return _google_services_cache
        return _build_google_services()


def _build_google_services():
    global _google_services_cache
    creds = None

    # 1. Most recently refreshed token, persisted to the DB by a previous
    #    run — checked first so a redeploy/cold-start on an ephemeral
    #    filesystem (Render, Cloud Run) doesn't fall back to the stale
    #    token baked into GOOGLE_TOKEN_B64 at deploy time.
    creds = _load_persisted_token()
    if creds:
        print("[Google Auth] Loaded credentials from bot_state (DB)")

    # 2. Env var (base64-encoded pickle) — the one-time seed value, set
    #    from refresh_token.py's output.
    if creds is None:
        token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
        if token_b64:
            import base64, io
            try:
                creds = pickle.load(io.BytesIO(base64.b64decode(token_b64)))
                print("[Google Auth] Loaded credentials from GOOGLE_TOKEN_B64")
            except Exception as e:
                print(f"[Google Auth] Failed to decode GOOGLE_TOKEN_B64: {e}")

    # 3. Fall back to token.pickle on disk — local dev only; this file
    #    does not survive a redeploy on a cloud host.
    if creds is None and os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)
        print("[Google Auth] Loaded credentials from token.pickle")

    # 4. Refresh if expired
    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            print("[Google Auth] Token refreshed successfully")
            _persist_token(creds)
            try:
                with open("token.pickle", "wb") as f:
                    pickle.dump(creds, f)
            except OSError:
                pass  # read-only/ephemeral filesystem — bot_state above is authoritative
        else:
            raise RuntimeError(
                "Google credentials are invalid and cannot be refreshed. "
                "Run refresh_token.py locally and set GOOGLE_TOKEN_B64 on Railway."
            )

    if creds is None:
        raise RuntimeError(
            "No Google credentials found. "
            "Run refresh_token.py locally and set GOOGLE_TOKEN_B64 on Railway."
        )

    calendar = build("calendar", "v3", credentials=creds)
    sheets   = build("sheets",   "v4", credentials=creds)
    tasks    = build("tasks",    "v1", credentials=creds)
    _google_services_cache = (calendar, sheets, tasks)
    return _google_services_cache
