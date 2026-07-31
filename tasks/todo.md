# Task List: Finish Calendar + More tabs

See `tasks/plan.md` for phase overview and `docs/SPEC.md` for full requirements.

---

## Task B1: Events routes

**Description:** Add id-based create/edit/delete for calendar events so the mobile Calendar tab
can mutate events it already displays, without the ambiguity of the existing keyword-match helpers.

**Acceptance criteria:**
- [ ] `features/calendar.py` has `delete_event_by_id(event_id) -> bool` and `edit_event_by_id(event_id, title=None, start=None, end=None, description=None) -> bool`, modeled on the existing `delete_event`/`edit_event` bodies minus the `events().list(q=keyword)` lookup
- [ ] `api.py` has `POST /api/events` (body `{message}` → `parse_event_with_ai` → `save_event`; or `{title, start, end?, description?}` directly), `PATCH /api/events/<id>`, `DELETE /api/events/<id>`
- [ ] `GET /api/events` reads an optional `?days=N` query param and passes it to `get_events_structured(days_ahead=N)` (currently ignores the param — hardcoded default only)
- [ ] All new routes return the existing `_ok`/`_err` envelope and 404 via `_err("NOT_FOUND", ...)` when the id doesn't exist

**Verification:**
- [ ] `pytest tests/test_api_events.py` passes
- [ ] Manual: `python app.py`, then curl `POST /api/events {"message": "lunch tomorrow 1pm"}` with bearer token, confirm a correctly-dated Google Calendar entry appears; `DELETE` it by the returned id and confirm it's gone from `GET /api/events`

**Dependencies:** None

**Files likely touched:**
- `features/calendar.py`
- `api.py`
- `tests/test_api_events.py` (new)

**Estimated scope:** M

---

## Task B2: Notes routes

**Description:** Add create/edit/delete routes for notes over the existing `save_note`/`edit_note`/`delete_note` functions.

**Acceptance criteria:**
- [ ] `api.py` has `POST /api/notes` (body `{message}` → `save_note`), `PATCH /api/notes/<index>` (→ `edit_note(new_content, index=)`), `DELETE /api/notes/<index>` (→ `delete_note(index=)`)
- [ ] `<index>` is an int path param; a non-existent index returns `_err("NOT_FOUND", ...)`, not a 500
- [ ] Missing `message`/`new_content` in the body returns `_err("VALIDATION_ERROR", ...)`, matching the pattern already used in `budget_post`/`chat`

**Verification:**
- [ ] `pytest tests/test_api_notes.py` passes
- [ ] Manual: curl create a note, confirm it appears in `GET /api/notes` and the Google Sheet, delete it, confirm it's gone from both

**Dependencies:** None

**Files likely touched:**
- `api.py`
- `tests/test_api_notes.py` (new)

**Estimated scope:** S

---

## Task B3: Ideas routes

**Description:** Mirror Task B2 for ideas over `save_idea`/`edit_idea`/`delete_idea`.

**Acceptance criteria:**
- [ ] `api.py` has `POST /api/ideas`, `PATCH /api/ideas/<index>`, `DELETE /api/ideas/<index>` — same shape and error handling as the notes routes
- [ ] Missing/not-found handling matches Task B2

**Verification:**
- [ ] `pytest tests/test_api_ideas.py` passes
- [ ] Manual: same curl sequence as B2 against `/api/ideas`

**Dependencies:** None (independent of B2, safe to parallelize if desired — but same file, so sequential commits recommended to avoid merge noise)

**Files likely touched:**
- `api.py`
- `tests/test_api_ideas.py` (new)

**Estimated scope:** S

---

## Task B4: Reminders delete route

**Description:** Add id-based delete for reminders — `get_reminders_structured` already returns a
real integer `id`, unlike notes/ideas, so this is a straightforward id lookup, not a keyword match.
Also add `POST /api/reminders` for creating one from natural language.

**Acceptance criteria:**
- [ ] `features/reminders.py` has `delete_reminder_by_id(reminder_id) -> bool`
- [ ] `api.py` has `DELETE /api/reminders/<id>` and `POST /api/reminders` (body `{message}` → `parse_reminder_with_ai` → `save_reminder`; or `{content, remindAt}` directly)
- [ ] Not-found id returns `_err("NOT_FOUND", ...)`

**Verification:**
- [ ] `pytest tests/test_api_reminders.py` passes
- [ ] Manual: curl create a reminder for 2 minutes out, confirm it lists in `GET /api/reminders` with the right `remindAt`, confirm the push arrives (this also exercises `check_and_send_reminders` — informal smoke test, not part of pytest)

**Dependencies:** None

**Files likely touched:**
- `features/reminders.py`
- `api.py`
- `tests/test_api_reminders.py` (new)

**Estimated scope:** S

---

## Task B5: News structured route

**Description:** Add a cheap, list-friendly news function separate from the existing slow
scrape+summarize `get_news`, plus routes for both the list and the detail view.

**Acceptance criteria:**
- [ ] `features/news.py` has `get_news_structured(topic, limit=5) -> list[dict]` — NewsAPI call only (reuse the existing request in `get_news`), returns `{title, source, publishedAt, url, description}` per article, no BeautifulSoup scrape, no `groq_complete` call
- [ ] Existing `get_news(topic)` is unchanged
- [ ] `api.py` has `GET /api/news?topic=` → `get_news_structured` and `GET /api/news/article?url=` → looks up the matching article and calls `get_news(topic)` for the full summarized text
- [ ] Missing `topic`/`url` query param returns `_err("VALIDATION_ERROR", ...)`

**Verification:**
- [ ] `pytest tests/test_api_news.py` passes (mock the NewsAPI HTTP call)
- [ ] Manual: curl `GET /api/news?topic=technology`, confirm 5 lightweight articles return quickly (no multi-second scrape delay)

**Dependencies:** None

**Files likely touched:**
- `features/news.py`
- `api.py`
- `tests/test_api_news.py` (new)

**Estimated scope:** S

---

## Task B6: Brainstorm + search routes

**Description:** Expose the two remaining backend features (`ai_brainstorm`, `semantic_search`)
that currently have no HTTP route at all.

**Acceptance criteria:**
- [ ] `api.py` has `POST /api/brainstorm` (body `{topic}` → `ai_brainstorm(topic)`) and `GET /api/search?q=` (→ `semantic_search(query)`)
- [ ] Missing `topic`/`q` returns `_err("VALIDATION_ERROR", ...)`

**Verification:**
- [ ] `pytest tests/test_api_brainstorm_search.py` passes
- [ ] Manual: curl both routes with a real topic/query and sanity-check the response shape

**Dependencies:** None

**Files likely touched:**
- `api.py`
- `tests/test_api_brainstorm_search.py` (new)

**Estimated scope:** S

---

## Task M1: Stack navigation + GestureHandlerRootView

**Description:** Two structural changes every later mobile task depends on: give the app a real
navigation stack (currently `<Slot />`, which has no back gesture/transition for screens pushed
outside the tabs group) and mount `GestureHandlerRootView` (dependency already installed, never
mounted — without it, swipe-to-delete silently no-ops on Android).

**Acceptance criteria:**
- [ ] `mobile/src/app/_layout.tsx` renders `<Stack screenOptions={{ headerShown: false }} />` from `expo-router` instead of `<Slot />`, with `(tabs)` as the entry screen
- [ ] The tree is wrapped in `GestureHandlerRootView` (`style={{ flex: 1 }}`)
- [ ] Per `mobile/AGENTS.md`, confirm the `Stack` + `(tabs)` group pairing against https://docs.expo.dev/versions/v57.0.0/ before assuming pre-SDK-57 patterns still apply

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: app launches, splash screen still resolves correctly (`AnimatedSplashOverlay` still renders — this task sits right next to it in `_layout.tsx`), all 4 tabs still switch, Home → Chat via ask-bar still pushes/navigates correctly

**Dependencies:** None

**Files likely touched:**
- `mobile/src/app/_layout.tsx`

**Estimated scope:** XS

---

## Task M2: `useResource` hook + `useHome` refactor

**Description:** Extract `useHome`'s fetch/refetch/optimistic-mutate pattern into a generic hook so
the seven new screens in Phases 3-4 don't each reimplement `useFocusEffect` + `loadedOnce` +
rollback-on-failure from scratch.

**Acceptance criteria:**
- [ ] New `mobile/src/hooks/useResource.ts` exports `useResource<T>(fetcher: () => Promise<T>)` returning `{ data, loading, error, refetch, mutate }` where `mutate` takes an optimistic updater plus the async call to run, and rolls the local state back to the last known-good value if the call rejects
- [ ] `useHome.ts` is rewritten on top of `useResource`, preserving its existing public shape (`data`, `loading`, `error`, `refetch`, `completeTaskOptimistic`) so `(tabs)/index.tsx` needs zero changes
- [ ] Behavior preserved exactly: skeleton only shows on first load (not on refocus refetch), task-complete still rolls back on API failure

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: Home still loads correctly, task checkbox still completes and rolls back correctly when the backend is killed mid-request

**Dependencies:** M1 (navigation must be stable before further hook/screen work layers on top)

**Files likely touched:**
- `mobile/src/hooks/useResource.ts` (new)
- `mobile/src/hooks/useHome.ts`

**Estimated scope:** S

---

## Task M3: Shared state components (ListScreen/ErrorState/EmptyState)

**Description:** Extract the loading/error/empty-state JSX blocks currently inlined in
`(tabs)/index.tsx:23-50` into reusable components so every new list screen (Calendar, Notes,
Ideas, Reminders, News) renders these states consistently instead of copy-pasting the block seven
times.

**Acceptance criteria:**
- [ ] New components: `ErrorState` (message + retry button, matches the existing inline error UI in `index.tsx`), `EmptyState` (icon/message for a zero-item list), `ListScreen` (a wrapper that takes `loading`/`error`/`data`/`refetch` and renders skeleton/error/empty/children appropriately)
- [ ] `(tabs)/index.tsx` is refactored to use these instead of its inline blocks, with pixel-identical rendered output (reuse existing theme tokens exactly as they're used today)

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: Home's loading/error/loaded states look and behave exactly as before this task (side-by-side check against a screenshot taken pre-refactor if in doubt)

**Dependencies:** M1

**Files likely touched:**
- `mobile/src/components/ErrorState.tsx` (new)
- `mobile/src/components/EmptyState.tsx` (new)
- `mobile/src/components/ListScreen.tsx` (new)
- `mobile/src/app/(tabs)/index.tsx`

**Estimated scope:** S

---

## Task M4: Shared interaction components (SwipeableRow/FAB/ComposeSheet)

**Description:** Build the three interaction primitives every write-capable screen in Phases 3-4
needs: a swipe-to-delete row, a floating action button, and a single-input compose modal that
posts free text to a backend AI-parsing route.

**Acceptance criteria:**
- [ ] `SwipeableRow` wraps `react-native-gesture-handler`'s `Swipeable`, reveals a delete action in `theme.colors.negative` on swipe, calls an `onDelete` prop
- [ ] `FAB` is a 42px round accent button matching the Chat composer's send button styling (`(tabs)/chat.tsx` / `Composer.tsx` for reference), accepts an `onPress` and an icon
- [ ] `ComposeSheet` is a modal with a single `TextInput`, a submit action, loading state while the POST is in flight, and calls an `onSubmit(message: string)` prop — no business logic inside it, purely presentational plus the text state
- [ ] Confirm gesture-handler `Swipeable` API against https://docs.expo.dev/versions/v57.0.0/ per `mobile/AGENTS.md` before implementing (RN Gesture Handler API has changed across versions)

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual: temporarily mount each component in one existing screen (e.g. wrap a Home task row in `SwipeableRow`) to confirm the gesture fires, then revert the temporary mount — these components have no real consumer until Phase 3

**Dependencies:** M1

**Files likely touched:**
- `mobile/src/components/SwipeableRow.tsx` (new)
- `mobile/src/components/FAB.tsx` (new)
- `mobile/src/components/ComposeSheet.tsx` (new)

**Estimated scope:** M

---

## Task M5: Calendar screen

**Description:** Replace the `PlaceholderScreen` at `(tabs)/calendar.tsx` with a real agenda view:
day-grouped events over a selectable range, swipe-to-delete, and a FAB that composes a new event
via natural language.

**Acceptance criteria:**
- [ ] New `mobile/src/api/events.ts` mirrors `api/tasks.ts`: `listEvents(days)`, `createEvent(message)`, `deleteEvent(id)`
- [ ] `mobile/src/api/types.ts` gains any request/response types events.ts needs beyond the existing `CalendarEvent`
- [ ] `(tabs)/calendar.tsx` shows events from `GET /api/events?days=N` grouped by day, with a 7/14/30 day selector; each row shows time (`formatEventTime`) and title; all-day events show a `Tag` instead of a time
- [ ] Uses `ListScreen`/`ErrorState`/`EmptyState` (M3) for loading/error/empty states, and `useResource` (M2) for data fetching
- [ ] Swipe-to-delete via `SwipeableRow` (M4) calls `DELETE /api/events/<id>`, then refetches
- [ ] `FAB` (M4) opens `ComposeSheet` (M4) → `POST /api/events {message}`, then refetches on success

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: Calendar tab loads real events grouped by day; creating "lunch tomorrow 1pm" via the FAB shows up after refetch; swiping an event away deletes it and it stays gone after backgrounding/reopening the app; airplane mode shows the error state with working retry

**Dependencies:** B1, M2, M3, M4

**Files likely touched:**
- `mobile/src/api/events.ts` (new)
- `mobile/src/api/types.ts`
- `mobile/src/app/(tabs)/calendar.tsx`

**Estimated scope:** M

---

## Task M6: Notes screen

**Description:** New detail screen for notes, reachable from the More hub (M13) and a Home shortcut
tile (M14) — list, create via compose, swipe-delete by index.

**Acceptance criteria:**
- [ ] New `mobile/src/api/notes.ts`: `listNotes()`, `createNote(message)`, `deleteNote(index)`
- [ ] New `mobile/src/app/notes.tsx` (outside the `(tabs)` group, pushed via the Stack from M1): list from `GET /api/notes`, `FAB` → `ComposeSheet` → `POST /api/notes`, `SwipeableRow` → `DELETE /api/notes/<index>`, all state via `useResource` + `ListScreen`
- [ ] After any mutation, the screen refetches rather than reordering the local list in place (index-addressing hazard — see plan.md Architecture Decisions)

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: navigate to `/notes` directly (temporary link or deep link during dev), create a note, confirm it appears, delete it, confirm it's gone from both the app and the Google Sheet

**Dependencies:** B2, M2, M3, M4

**Files likely touched:**
- `mobile/src/api/notes.ts` (new)
- `mobile/src/app/notes.tsx` (new)

**Estimated scope:** S

---

## Task M7: Ideas screen

**Description:** Mirror Task M6 for ideas.

**Acceptance criteria:**
- [ ] New `mobile/src/api/ideas.ts`: `listIdeas()`, `createIdea(message)`, `deleteIdea(index)`
- [ ] New `mobile/src/app/ideas.tsx` — identical structure to `notes.tsx` against `/api/ideas`

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: same sequence as M6 against `/ideas`

**Dependencies:** B3, M2, M3, M4

**Files likely touched:**
- `mobile/src/api/ideas.ts` (new)
- `mobile/src/app/ideas.tsx` (new)

**Estimated scope:** S

---

## Task M8: Reminders screen

**Description:** Detail screen for reminders — list, create via natural-language compose,
swipe-delete by real id (unlike notes/ideas, reminders have a stable database id).

**Acceptance criteria:**
- [ ] New `mobile/src/api/reminders.ts`: `listReminders()`, `createReminder(message)`, `deleteReminder(id)`
- [ ] New `mobile/src/app/reminders.tsx`: list from `GET /api/reminders` using `formatReminderTime` for labels, `FAB` → `ComposeSheet` → `POST /api/reminders`, `SwipeableRow` → `DELETE /api/reminders/<id>`

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: create a reminder, confirm it lists with the correct relative time label, delete it, confirm gone

**Dependencies:** B4, M2, M3, M4

**Files likely touched:**
- `mobile/src/api/reminders.ts` (new)
- `mobile/src/app/reminders.tsx` (new)

**Estimated scope:** S

---

## Task M9: News screen

**Description:** Topic search over the lightweight news list, with tap-through to the slow
scraped+summarized detail view.

**Acceptance criteria:**
- [ ] New `mobile/src/api/news.ts`: `searchNews(topic)`, `getNewsArticle(url)`
- [ ] New `mobile/src/app/news.tsx`: topic `TextInput` (not a `ComposeSheet` — this is a search, not a create action) → article list from `GET /api/news?topic=`; tapping an article shows a loading state then the full summarized text from `GET /api/news/article?url=`
- [ ] Uses `ListScreen`/`ErrorState`/`EmptyState` for the list states

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: search a topic, confirm article list appears quickly (no multi-second wait — that's the point of B5's split), tap one, confirm the slower summarized detail loads with its own loading indicator

**Dependencies:** B5, M2, M3

**Files likely touched:**
- `mobile/src/api/news.ts` (new)
- `mobile/src/app/news.tsx` (new)

**Estimated scope:** S

---

## Task M10: Brainstorm screen

**Description:** Simple topic-in, AI-response-out screen over `POST /api/brainstorm`.

**Acceptance criteria:**
- [ ] New `mobile/src/api/brainstorm.ts`: `brainstorm(topic)`
- [ ] New `mobile/src/app/brainstorm.tsx`: topic input, submit, renders the returned text response with a loading state while awaiting

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: submit a topic, confirm a response renders

**Dependencies:** B6, M2

**Files likely touched:**
- `mobile/src/api/brainstorm.ts` (new)
- `mobile/src/app/brainstorm.tsx` (new)

**Estimated scope:** XS

---

## Task M11: Budget screen

**Description:** Detail view for budget, reusing the existing `BudgetCard` component (already used
on Home) rather than building new budget UI.

**Acceptance criteria:**
- [ ] New `mobile/src/api/budget.ts`: `getBudget()`, `recomputeBudget(message)`
- [ ] New `mobile/src/app/budget.tsx`: renders `GET /api/budget` through the existing `BudgetCard` component; a compose action for `POST /api/budget {message}` to recompute, refetching on success

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: screen shows the same budget data Home shows; recomputing via a new message updates both this screen and Home after refetch

**Dependencies:** M2 (no new backend route — `GET`/`POST /api/budget` already exist)

**Files likely touched:**
- `mobile/src/api/budget.ts` (new)
- `mobile/src/app/budget.tsx` (new)

**Estimated scope:** XS

---

## Task M12: Search screen

**Description:** Semantic search UI over `GET /api/search?q=`.

**Acceptance criteria:**
- [ ] New `mobile/src/api/search.ts`: `search(query)`
- [ ] New `mobile/src/app/search.tsx`: query input, results list tagged by source type (note/idea/etc., per `semantic_search`'s return shape), uses `ListScreen`/`EmptyState`

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: search a term that matches an existing note, confirm it surfaces with its source tag

**Dependencies:** B6, M2, M3

**Files likely touched:**
- `mobile/src/api/search.ts` (new)
- `mobile/src/app/search.tsx` (new)

**Estimated scope:** XS

---

## Task M13: More hub screen

**Description:** Replace the `PlaceholderScreen` at `(tabs)/more.tsx` with a grid hub linking to
every detail screen built in M6-M12. Built last in this phase so every link resolves to a real
screen on first render.

**Acceptance criteria:**
- [ ] `(tabs)/more.tsx` renders a section-titled grid of `ShortcutTile`s (component already supports `onPress`) routing to `/notes`, `/ideas`, `/reminders`, `/news`, `/brainstorm`, `/budget`, `/search`
- [ ] Visual treatment matches the existing Nocturne token usage seen elsewhere (spacing, radius, icon sizing consistent with Home's shortcut row)

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: every tile in More navigates to its screen and back correctly (exercises the Stack from M1)

**Dependencies:** M6, M7, M8, M9, M10, M11, M12

**Files likely touched:**
- `mobile/src/app/(tabs)/more.tsx`

**Estimated scope:** S

---

## Task M14: Wire Home's dead affordances

**Description:** Small, high-visibility fixes to `(tabs)/index.tsx` now that every target screen
exists.

**Acceptance criteria:**
- [ ] The four `ShortcutTile`s (Notes/Ideas/News/Brainstorm) get `onPress` routing to their respective screens
- [ ] "See all" navigates to a tasks list (reuse `ListScreen` pattern; a minimal `/tasks` screen if one doesn't already exist as part of this work, listing `GET /api/tasks`)
- [ ] `ReminderStrip` and the bell button both route to `/reminders`
- [ ] The bell's unread dot reflects whether `data.reminders` is non-empty, instead of always rendering
- [ ] `"Good morning,"` is replaced with a greeting derived from `new Date().getHours()` (morning/afternoon/evening breakpoints)

**Verification:**
- [ ] `npx tsc --noEmit` passes
- [ ] Manual on-device: every tappable element on Home that previously did nothing now navigates correctly; greeting text changes correctly if the device clock is adjusted across a breakpoint

**Dependencies:** M6, M7, M8, M9, M10, M13

**Files likely touched:**
- `mobile/src/app/(tabs)/index.tsx`
- `mobile/src/app/tasks.tsx` (new, only if a tasks list screen doesn't already exist)

**Estimated scope:** S
