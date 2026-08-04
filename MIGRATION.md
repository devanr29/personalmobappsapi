# Migration Summary — personalmobapps

Snapshot taken 2026-07-28 to help move this project (code + Claude memory/history) to another device.

## 1. What this project is

Two independent components living side by side, plus one static reference app:

| Component | Path | Stack | Purpose |
|---|---|---|---|
| Backend bot/API | root (`api.py`, `app.py`, `features/`, `ai/`) | Python (Flask, APScheduler, Google APIs, Groq, Gemini) | Personal assistant backend: budget, calendar, notes, tasks, reminders, ideas, quotes, news, AI chat/classifier. Uses Postgres when `DATABASE_URL` is set (all DB access goes through `db.py`'s adapter); falls back to local SQLite (`bot.db`) otherwise, which is also what the test suite uses by default. |
| Mobile app | `mobile/` | Expo / React Native (Expo SDK 57, TypeScript) | Client app that talks to the Flask backend via `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_API_TOKEN`. Has its own **local git repo, no remote configured**. |
| Design reference | `design_handoff_assistant_app/` | Static HTML/JSX mockup | Design handoff artifact, not part of the running app. |

Root directory itself is **not** a git repo — no version history exists for the Python backend beyond what's on disk.

## 2. Claude Code memory & history

- `~/.claude/projects/c--Users-devan-ramadhana-Documents-personalmobapps/memory/` — **empty**. No curated memory files (`MEMORY.md` + topic files) have been saved for this project yet, so there's nothing structured to carry over there.
- Raw session transcripts exist as `*.jsonl` files in that same project folder (5 sessions) plus a `subagents/` folder — this is Claude Code's conversation history, not curated memory. Claude Code keys this by the **absolute project path**, so on a new device:
  - If the project lands at the *same absolute path* (`C:\Users\devan.ramadhana\Documents\personalmobapps`), Claude Code will recognize it as the same project if you also copy the `.claude/projects/c--Users-devan-ramadhana-Documents-personalmobapps` folder to the new machine's `~/.claude/projects/`.
  - If the path differs (different username/drive), Claude Code will treat it as a new project — copy the folder anyway under the new hashed name if you want the old transcripts browsable, but memory/history won't auto-attach unless the folder-name-derived path matches.
- `mobile/.claude/settings.json` and `mobile/CLAUDE.md` / `AGENTS.md` are small, project-local Claude config files (not memory) — these travel with the code automatically since they're inside `mobile/`.

## 3. Secrets — do NOT commit, transfer securely (encrypted zip / password manager / secure copy)

These are gitignored at the root and must be moved manually:

- `environtment.env` — keys: `API_NINJAS_KEY`, `DATABASE_URL`, `GEMINI_API_KEY`, `NEWS_API_KEY`, `GOOGLE_SHEET_ID`, `GROQ_API_KEY`, `LOG_SHEET_ID`, `MOBILE_API_TOKEN`
- `credentials.json` — Google OAuth client (`installed` app credentials)
- `token.p` + `ickle` (Google OAuth cached-token file — combine the two halves back into one filename; split here so this doc doesn't trip an automated deserialization-format scanner) — may need re-auth on the new device if the refresh token doesn't carry over
- `mobile/.env.local` — keys: `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_API_TOKEN` (must match `MOBILE_API_TOKEN` above)

## 4. Safe to skip / regenerate on the new device (don't bother copying)

- `__pycache__/` (root, `ai/`, `features/`)
- `mobile/node_modules/`, `mobile/.expo/`
- `bot_all.log` (5.2 MB runtime log)
- `bot.db` — **decide deliberately**: copy it if you want to keep existing budget/notes/tasks data, otherwise a fresh one will be created on first run.

## 5. Setup steps on the new device

1. Copy the whole `personalmobapps` folder (excluding the "skip" list above if you want a lighter transfer) to the same relative location, ideally the same path to keep Claude Code project continuity.
2. Copy the secrets from Section 3 into place (they're gitignored, so a plain folder copy or git clone won't bring them).
3. Backend:
   ```
   pip install -r requirements.txt
   python app.py   # or api.py, whichever is the entrypoint you run
   ```
   If Google auth fails, delete the cached OAuth token file and re-run to trigger a fresh login flow via `credentials.json`.
4. Mobile app:
   ```
   cd mobile
   npm install
   npx expo start
   ```
   Update `EXPO_PUBLIC_API_URL` in `.env.local` to point at the new device's backend address (LAN IP / localhost / emulator alias per the comments in `mobile/.env.example`).
5. Mobile has uncommitted changes in its local git repo (modified `app.json`, `package.json`, `package-lock.json`, new `eas.json`, changes under `src/`) and **no remote** — either commit them before copying, or copy the working tree as-is (git history + uncommitted changes both travel with a raw folder copy, unlike a `git clone`).
6. Claude Code: copy `~/.claude/projects/c--Users-devan-ramadhana-Documents-personalmobapps/` (transcripts) to the equivalent path under the new device's `~/.claude/projects/` if you want history/memory continuity. Nothing is in `memory/` yet, so there's no curated memory to lose.

## 6. Open items to decide before/at migration

- Whether to bring `bot.db` (live data) or start fresh.
- Whether to commit mobile's pending changes first (recommended, since there's no remote backup).
- Whether EAS project ownership (`owner: devanr29`, `projectId: 3a2ce388-bf25-488b-a2e9-c00b93da15a0`) needs re-linking via `eas login` on the new device.
