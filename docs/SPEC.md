# Finish Calendar + More tabs (read/write)

## Context

The Android dev build runs on a real device. Home and Chat are fully wired to the Flask backend,
but `mobile/src/app/(tabs)/calendar.tsx` and `mobile/src/app/(tabs)/more.tsx` are still one-line
`PlaceholderScreen` stubs, and the four shortcut tiles on Home (Notes / Ideas / News / Brainstorm)
render with no `onPress`. Two of four tabs are dead and half the backend's features have no way in
except by typing a sentence into Chat.

This spec closes that gap: every backend feature gets a real screen with create and delete.

**Out of scope for this spec:** deploying the backend off the LAN IP (Render hosting, Postgres
migration, keep-alive cron). That requires external account creation and manual dashboard steps
an autonomous agent can't perform, and is tracked separately in
`C:\Users\devan.ramadhana\.claude\plans\already-run-dev-via-effervescent-stream.md` (Phase 6).

## What already exists — reuse, don't rebuild

- **Backend feature functions are all written**: `save_note`, `delete_note(index=)`, `edit_note`
  (and the same trio for ideas), `save_reminder`, `delete_reminder`, `save_event`, `delete_event`,
  `edit_event`, `get_news`, `ai_brainstorm`, `semantic_search`. Missing piece: HTTP routes over them.
- **`*_structured()` variants already return mobile-shaped dicts**: `get_events_structured`,
  `get_notes_structured`, `get_ideas_structured`, `get_reminders_structured`,
  `get_tasks_structured`. GET routes for all of these already exist in `api.py`.
- **Natural-language parsers exist**: `parse_reminder_with_ai` (`features/reminders.py:14`) and
  `parse_event_with_ai` (`features/calendar.py:13`). Use these instead of building date/time
  picker UI — a compose sheet becomes one `TextInput`.
- **Mobile primitives exist**: `Card`, `Tag`, `TaskRow`, `Skeleton`, `HomeSkeleton`, `StatCard`,
  `ReminderStrip`, `ShortcutTile` (already accepts an optional `onPress`), the full Nocturne token
  set in `mobile/src/theme/tokens.ts`, and `utils/date.ts` / `currency.ts` / `text.ts`.
- **`google_auth.py` already reads `GOOGLE_TOKEN_B64`** — no auth work needed.

## Requirements

### R1 — Backend routes (api.py)

All new routes use the existing `_ok` / `_err` envelope; auth (`_check_auth`) and CORS (`_cors`)
already apply globally. Notes and ideas are index-addressed (Google Sheets rows, no stable id —
see `features/notes.py:78`), so every mutation must be followed by a client refetch, never an
optimistic reorder.

| Route | Delegates to |
|---|---|
| `POST /api/events` | `parse_event_with_ai(message)` when body is `{message}`, else `save_event(title, start, end, description)` |
| `PATCH /api/events/<id>` | new `edit_event_by_id` |
| `DELETE /api/events/<id>` | new `delete_event_by_id` |
| `GET /api/events?days=N` | `get_events_structured(days_ahead=N)` |
| `POST /api/notes` | `save_note(text)` |
| `PATCH /api/notes/<index>` | `edit_note(new_content, index=)` |
| `DELETE /api/notes/<index>` | `delete_note(index=)` |
| `POST/PATCH/DELETE /api/ideas[...]` | `save_idea` / `edit_idea` / `delete_idea` |
| `POST /api/reminders` | `parse_reminder_with_ai(message)` then `save_reminder`, or `{content, remindAt}` directly |
| `DELETE /api/reminders/<id>` | new `delete_reminder_by_id` |
| `GET /api/news?topic=` | new `get_news_structured` |
| `GET /api/news/article?url=` | existing `get_news(topic)` |
| `POST /api/brainstorm` | `ai_brainstorm(topic)` |
| `GET /api/search?q=` | `semantic_search(query)` |

New helpers needed:
- `features/calendar.py`: `delete_event_by_id(event_id) -> bool`, `edit_event_by_id(event_id, title=None, start=None, end=None, description=None) -> bool` — same bodies as the existing keyword versions minus the `events().list(q=keyword)` lookup.
- `features/reminders.py`: `delete_reminder_by_id(reminder_id) -> bool`.
- `features/news.py`: `get_news_structured(topic, limit=5) -> list[dict]` returning `{title, source, publishedAt, url, description}` per article — NewsAPI call only, no scrape, no LLM summarization (too slow to fan out across a list). Leave `get_news(topic)` untouched.

### R2 — Mobile foundations

- `mobile/src/app/_layout.tsx`: replace `<Slot />` with `<Stack screenOptions={{ headerShown: false }} />` so screens pushed outside the tabs group get back gesture/transition.
- Wrap the tree in `GestureHandlerRootView` (dependency exists, never mounted) — without it swipe-to-delete silently no-ops on Android.
- Extract `mobile/src/hooks/useHome.ts`'s pattern (`useFocusEffect` refetch, `loadedOnce` ref, optimistic mutate + rollback) into a generic `useResource<T>(fetcher)` in `useResource.ts`; rewrite `useHome` on top of it.
- Extract the inline loading/error/empty blocks from `(tabs)/index.tsx:23-50` into shared `ListScreen`, `ErrorState`, `EmptyState` components.
- New shared components: `SwipeableRow` (gesture-handler `Swipeable`, delete action in `colors.negative`), `FAB` (42px round accent), `ComposeSheet` (modal, single `TextInput`, posts to a `POST` route).
- New API modules mirroring `api/tasks.ts`: `events.ts`, `notes.ts`, `ideas.ts`, `reminders.ts`, `news.ts`, `brainstorm.ts`. Extend `api/types.ts` with `NewsArticle` and request payload types.

### R3 — Calendar tab

Replace `(tabs)/calendar.tsx` with an agenda list grouped by day (`GET /api/events?days=N`, selector for 7/14/30). Time on the left (`formatEventTime`), all-day events shown with a `Tag`. Swipe to delete → `DELETE /api/events/<id>`. FAB → `ComposeSheet` → `POST /api/events {message}`.

### R4 — More tab + detail screens

Replace `(tabs)/more.tsx` with a hub grid of `ShortcutTile`s routing to:
- `notes.tsx`, `ideas.tsx` — list + swipe-delete by index + FAB compose
- `reminders.tsx` — list + swipe-delete by id + FAB compose (`formatReminderTime` for labels)
- `news.tsx` — topic search → article list (`GET /api/news?topic=`) → tap for summarized detail (`GET /api/news/article?url=`)
- `brainstorm.tsx` — topic input → `POST /api/brainstorm`
- `budget.tsx` — `GET /api/budget` into `BudgetCard`; recompute via `POST /api/budget {message}`
- `search.tsx` — `GET /api/search?q=`, results tagged by source type

Settings (theme config wiring) is optional — drop if scope tightens.

Per `mobile/AGENTS.md`, check https://docs.expo.dev/versions/v57.0.0/ before using any Expo API new to this codebase.

### R5 — Wire Home's dead affordances

In `(tabs)/index.tsx`: the four `ShortcutTile`s get `onPress` to the R4 screens; "See all" links to a tasks list; `ReminderStrip` and the bell route to `reminders.tsx` (unread dot reflects real reminder count); `"Good morning,"` derives from `new Date().getHours()`.

## Testing

Add `pytest` + Flask test client coverage for the new R1 routes (auth required, validation errors,
success envelope shape) — mock the backend feature functions rather than hitting Google APIs.
No RN component test framework exists in this project (no jest config) and none is being added;
mobile screens are verified by running the dev client on-device per the Verification section below.

## Verification

**Backend**, before touching mobile: run each new route with curl + bearer token — create a note,
confirm it's listed, delete it, confirm it's gone. Repeat for ideas, reminders, events. Confirm
`POST /api/events {"message": "lunch tomorrow 1pm"}` produces a correctly-dated Calendar entry.

**Mobile**: `npx expo start --dev-client` against the connected device. Per screen: skeleton → data
→ create via FAB → appears after refetch → swipe-delete → gone and stays gone after
backgrounding/reopening. Airplane mode shows the error state with working retry, not an infinite
skeleton.

**Regression**: Home and Chat unchanged after the `useHome` refactor and `Slot` → `Stack` switch —
tab switching, Home → Chat ask-bar push, task checkbox rollback (kill backend, tap checkbox,
confirm revert).
