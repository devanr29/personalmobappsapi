# Implementation Plan: Finish Calendar + More tabs

Source spec: `docs/SPEC.md`. Full context/rationale also in
`C:\Users\devan.ramadhana\.claude\plans\already-run-dev-via-effervescent-stream.md` (Phases 1-5;
Phase 6/Render deploy is out of scope here).

## Overview

Two of the app's four tabs (`Calendar`, `More`) are `PlaceholderScreen` stubs, and Home's four
shortcut tiles have no `onPress`. The backend already has feature functions and `*_structured()`
read variants for everything needed — what's missing is write routes (create/delete) and the
mobile screens/hooks to call them. Backend ships first since every mobile screen depends on its
routes; mobile foundations (navigation, shared hook, shared components) ship before the individual
screens that reuse them.

## Architecture Decisions

- **Notes/ideas are index-addressed, not id-addressed** (Google Sheets rows, no stable key —
  `features/notes.py:78`). Every mobile mutation for these two resources must trigger a refetch,
  never an optimistic list reorder — resolved by having their screens use `useResource`'s refetch
  path, not `completeTaskOptimistic`-style local mutation.
- **`get_news_structured` is a new, separate function from `get_news`** — the existing `get_news`
  scrapes + runs an LLM summarization per article, too slow to fan out across a list. The list view
  needs a cheap NewsAPI-only call; the detail view keeps using the slow, rich one.
- **`useResource<T>` generalizes `useHome`'s existing pattern** (`useFocusEffect` refetch,
  `loadedOnce` ref to avoid skeleton-flash on refocus, optimistic mutate + rollback) rather than
  each new screen reimplementing focus-refetch logic.
- **pytest + Flask test client for backend routes only.** No RN test framework exists in this repo
  (no jest config) and none is being introduced — mobile screens are verified by running the dev
  client on the connected Android device.

## Task List

### Phase 1: Backend routes (Python — api.py + features/*.py)

- [ ] Task B1: Events routes
- [ ] Task B2: Notes routes
- [ ] Task B3: Ideas routes
- [ ] Task B4: Reminders delete route
- [ ] Task B5: News structured route
- [ ] Task B6: Brainstorm + search routes

### Checkpoint: Backend complete
- [ ] `pytest` passes for all six new test files
- [ ] `python app.py` starts clean; manual curl smoke test against each new route (see spec Verification section) succeeds
- [ ] Review with human before starting mobile work

### Phase 2: Mobile foundations (mobile/src/**)

- [ ] Task M1: Stack navigation + GestureHandlerRootView
- [ ] Task M2: `useResource` hook + `useHome` refactor
- [ ] Task M3: Shared state components (ListScreen/ErrorState/EmptyState)
- [ ] Task M4: Shared interaction components (SwipeableRow/FAB/ComposeSheet)

### Checkpoint: Foundations complete
- [ ] `npx tsc --noEmit` passes
- [ ] App builds and runs on device; Home and Chat behave identically to before this phase (tab switching, ask-bar push, task checkbox + optimistic rollback on kill-backend)
- [ ] Review with human before starting Calendar/More screens

### Phase 3: Calendar tab

- [ ] Task M5: Calendar screen (events API module + agenda UI)

### Phase 4: More tab detail screens

- [ ] Task M6: Notes screen
- [ ] Task M7: Ideas screen
- [ ] Task M8: Reminders screen
- [ ] Task M9: News screen
- [ ] Task M10: Brainstorm screen
- [ ] Task M11: Budget screen
- [ ] Task M12: Search screen
- [ ] Task M13: More hub screen

### Phase 5: Home wiring

- [ ] Task M14: Wire Home's dead affordances

### Checkpoint: Complete
- [ ] Every PlaceholderScreen replaced; every shortcut tile/link navigates somewhere real
- [ ] Full manual verification pass per `docs/SPEC.md` Verification section (skeleton→data→create→delete→persist-after-background, airplane-mode error state)
- [ ] `npx tsc --noEmit` and `pytest` both pass
- [ ] Ready for human review

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `Slot` → `Stack` change in `_layout.tsx` breaks existing tab navigation | High | Task M1 is isolated and immediately followed by a manual regression pass before any further mobile work proceeds |
| Notes/ideas index-based deletes race if list changed since last fetch (Sheets row shifted) | Medium | Screens always refetch after mutation instead of trusting the old index list; document this in each screen's compose/delete handler |
| `parse_event_with_ai` / `parse_reminder_with_ai` misparse natural language | Medium | Not a code defect — mitigate via the manual verification step in B1/B4 (confirm a real Calendar entry lands with the correct date) rather than trying to unit-test LLM output |
| Expo SDK 57 API surface differs from training-era assumptions (gesture-handler, `expo-router` Stack) | Medium | Per `mobile/AGENTS.md`, check https://docs.expo.dev/versions/v57.0.0/ before using any Expo API new to this codebase, during M1 and M4 |
| Backend root just became a fresh git repo (this session) — no history to fall back on before the baseline commit | Low | Baseline commit already made (`6d10f2d`); every task below gets its own commit on top of it |

## Open Questions

None outstanding — scope, hosting, and testing approach were confirmed with the user before this
plan was written. Settings/theme-picker screen was explicitly marked optional in the spec and is
dropped from this task list to keep scope tight.
