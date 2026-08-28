"""Walks the mobile REST API and reports pass/fail per route — a five-second
sanity check that doesn't need the phone or the emulator. Exercises only
GETs (safe, no side effects); write endpoints aren't included here.

Usage:
    python scripts/smoke.py
        # http://localhost:5000, token read from environtment.env

    python scripts/smoke.py --url https://your-app.onrender.com --token <MOBILE_API_TOKEN>
        # point at a deployed backend, e.g. right after a Render deploy
"""
import argparse
import os
import sys

import requests

# Read-only routes, mirroring api.py and features/budget/blueprint.py.
# /api/health is exempt from auth (api.py) but included anyway to confirm
# the process is actually up before the auth'd routes are judged.
ROUTES = [
    "/api/health",
    "/api/home",
    "/api/tasks",
    "/api/events",
    "/api/reminders",
    "/api/notes",
    "/api/ideas",
    "/api/news",
    "/api/search?q=test",
    "/api/budget/ping",
    "/api/budget",
    "/api/budget/setup/status",
    "/api/budget/wallets",
    "/api/budget/categories",
    "/api/budget/bills",
    "/api/budget/goals",
    "/api/budget/alerts",
    "/api/budget/alerts/prefs",
    "/api/budget/transactions",
    "/api/budget/insights",
    "/api/budget/sync/wallet/status",
]


def _load_token_from_env_file() -> str:
    """Best-effort read of MOBILE_API_TOKEN straight from environtment.env,
    without importing config.py — that module builds the Gemini/Groq
    clients at import time, which is unnecessary weight for a route-only
    smoke test and would require those keys to be present too."""
    path = os.path.join(os.path.dirname(__file__), "..", "environtment.env")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("MOBILE_API_TOKEN="):
                return line.strip().split("=", 1)[1]
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("SMOKE_API_URL", "http://localhost:5000"))
    parser.add_argument("--token", default=os.environ.get("MOBILE_API_TOKEN") or _load_token_from_env_file())
    args = parser.parse_args()

    if not args.token:
        print("No MOBILE_API_TOKEN found (checked --token, $MOBILE_API_TOKEN, environtment.env). Aborting.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {args.token}"}
    base = args.url.rstrip("/")
    print(f"Smoke-testing {base} ({len(ROUTES)} routes)\n")

    failures = 0
    for path in ROUTES:
        url = f"{base}{path}"
        resp = None
        detail = ""
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            passed = resp.ok
            detail = f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            passed = False
            detail = str(e)

        print(f"[{'PASS' if passed else 'FAIL'}] {path:40s} {detail}")
        if not passed:
            failures += 1

    total = len(ROUTES)
    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
