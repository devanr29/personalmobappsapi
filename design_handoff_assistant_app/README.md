# Handoff: Personal Assistant — Mobile App (Home + Chat)

## Overview
This bundle contains the mobile-app UI for turning the existing **WhatsApp AI assistant** (Flask + Groq backend, Google Tasks/Calendar/Sheets sync) into a native mobile app. It covers the two landing screens delivered in this round:

1. **Home / Dashboard** — the app's default tab; an at-a-glance view of the assistant's features.
2. **Chat** — the AI assistant conversation (the heart of the current product), one tab in a 4-tab bar.

The remaining features already in the backend (Calendar/Events, Reminders, Notes, Ideas, Budget config, News, Quotes, Brainstorm, semantic Memory search) are surfaced as entry points on Home and behind the **Calendar** and **More** tabs — those screens are not yet designed.

## About the Design Files
The files in this bundle are **design references created in HTML** (a Design Component prototype) — they show the intended look and behavior, **not** production code to copy directly. The task is to **recreate these designs in the target mobile environment** — most likely **React Native (Expo)** or **Flutter**, since the goal is a native mobile app — using that environment's own components, navigation, and styling. The Flask/Groq backend and Green API/Google integrations stay; the app is a new client for the same feature set (replace the WhatsApp/Green API messaging layer with in-app chat + REST/websocket calls to the existing intent → feature functions).

- `Assistant App.dc.html` — the prototype. Both phone screens are laid out side by side on a canvas.
- `android-frame.jsx` — the Android device bezel used only to frame the mockup (status bar, gesture nav). **Do not port this** — the real app runs inside the OS chrome.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, radii, and content are as intended. Recreate pixel-accurately, mapping the tokens below to the app's theme system. Copy is in English; finance is in IDR (Rupiah), matching the backend's Asia/Jakarta + Rupiah context.

## Design System
Built on the **Nocturne** dark design system. All values below are the concrete resolved tokens.

### Colors
- Ground / background: `#161826`
- Surface (cards, bars, bubbles): `#232532`
- Text (primary): `#e9e9ed`
- Accent (blurple): `#9184d9`
- Divider: `rgba(233,233,237,0.16)`
- Neutral ramp: 100 `#f3f5fe` · 200 `#e4e7f5` · 300 `#cfd3e5` · 400 `#b2b6ca` · 500 `#9397ab` · 600 `#75798c` · 700 `#595d6c` · 800 `#3f424d` · 900 `#292b31`
- Accent ramp: 100 `#f5f4ff` · 200 `#e7e5fe` · 300 `#d2cefd` · 400 `#b5abfc` · 500 `#968ae0` · 600 `#796cbf` · 700 `#5d5294` · 800 `#423a6a` · 900 `#2b2741`
- Positive/online dot: `#4ea87a` · Negative (budget deduction): `#d98c8c`
- Canvas backdrop (mockup only, not in app): `#0e0f18`

### Typography
- Family: **Inter** (400/500/600/700). Headings weight 500 (never heavier). Letter-spacing on large headings ≈ `-0.015em`.
- Greeting name 23px/500 · card titles 15–17px/500 · body 14px/400 · meta 11–13px/400 · tab labels 10.5px · big number (budget) 27px/500.

### Spacing (Nocturne 0.70× scale)
`2.8 / 5.6 / 8.4 / 11.2 / 16.8 / 22.4` px. Screen padding 16px horizontal, card padding 14–15px, inter-card gap 16px.

### Radius
sm `4px` · md `8px` (cards, tiles, tags) · lg `14px` (chat bubbles, ask-bar, elevated panels). Chat bubbles use an asymmetric radius (tail corner = sm): user `lg lg sm lg`, assistant `lg lg lg sm`. Input pill = 22px. Avatars/FAB = 50%.

### Elevation
Dark-ground elevation is a hairline edge + ambient shadow, never a heavy drop shadow:
- sm: `0 0 0 1px #3f424d`
- md: `0 0 0 1px #595d6c, 0 6px 18px rgba(0,0,0,0.55)`
- Bar separators: 1px divider line only.

### Icons
**Phosphor Icons** throughout. Names used: `house`, `chat-circle-dots`, `calendar-blank`, `squares-four` (tabs); `bell`, `sparkle`(fill), `microphone`, `check-square`, `calendar-check`, `check`(bold), `wallet`, `alarm`(fill), `caret-right`/`caret-left`, `quotes`(fill), `note`, `lightbulb`, `newspaper`, `brain`, `dots-three-vertical`, `check-circle`(fill), `paperclip`, `paper-plane-right`(fill). Use `phosphor-react-native` (RN) or `phosphor_flutter` (Flutter).

## Screens / Views

### 1. Home / Dashboard
**Purpose:** landing tab; quick status of tasks, next event, budget, reminders + shortcuts into every feature and the assistant.
**Layout:** vertical scroll, 16px horizontal padding, 16px gap between blocks; fixed bottom tab bar. Top-to-bottom:
- **Greeting header** (row): left column "Selamat pagi," (13px, neutral-500) / "Devan" (23px/500) / date "Senin, 13 Juli" (12px neutral-500). Right: 38px round bell button (surface, sm shadow) with a 6px accent unread dot top-right; 42px round avatar "D" (accent-800 bg, accent-100 text).
- **Ask bar**: full-width lg-radius surface pill, sparkle(fill, accent) + "Tanya apa saja ke asisten…" (neutral-500) + microphone. Tapping opens Chat.
- **Section header**: "Hari Ini" (16px/500) + "Lihat semua" link (12px accent).
- **Two stat cards** (grid 1fr 1fr, 12px gap, md radius, surface, sm shadow, 14px pad): (a) check-square icon + big "3" + "Active tasks"; (b) calendar-check icon + "13:00" + "Product team meeting".
- **Task list card** (surface, md, sm shadow): 3 rows, each a 16px checkbox + label. Row 1 unchecked + `tag-accent` "Today". Row 3 checked (accent-filled box, bold check, 0.5 opacity, line-through).
- **Budget card**: wallet icon + "Budget harian" + "12 hari ke gajian"; big "Rp 87,500" + "/day"; 6px progress track (neutral-800) filled 58% accent; footer "Left Rp 1,050,000" / "of Rp 2,500,000".
- **Reminder strip**: accent-900 bg, 1px accent-800 edge; alarm(fill, accent-300) + "Take medicine" (accent-100) / "Later · 20:00" (accent-300) + caret-right.
- **Quote card**: quotes(fill, accent) + italic quote (neutral-200) + "— Mark Twain" (neutral-500).
- **Shortcuts grid** (4 cols, 10px gap): square surface tile (aspect 1, md radius, accent icon) + label under. Notes(note) / Ideas(lightbulb) / News(newspaper) / Brainstorm(brain).

### 2. Chat
**Purpose:** converse with the AI assistant; it routes to the same intents as the backend classifier and renders rich results (task added, budget breakdown, quote, etc.).
**Layout:** fixed header, scrolling thread, fixed composer + tab bar.
- **Header** (surface, 1px divider under): caret-left back + 38px round avatar (accent-800, sparkle-fill accent-200) + "Assistant" (15px/500) with "● Online" (green dot #4ea87a) + dots-three-vertical.
- **Thread** (16/14px pad, 12px gap): centered day label "Today" (11px neutral-600). Message bubbles max-width ~80–88%:
  - **User** — right-aligned, `accent-800` bg, `accent-100` text, radius `lg lg sm lg`.
  - **Assistant** — left-aligned, `surface` bg, sm shadow, radius `lg lg lg sm`.
  - Rich assistant bubbles: **task confirmation** (✅ + "Juga masuk ke Google Tasks"); **budget breakdown card** (title "💰 Budget Breakdown", 12-days subline, divider, right-aligned rows Money in hand / Total deductions in `#d98c8c` / Free money left, divider, accent-900 highlight strip with check-circle + "Daily budget **Rp 87,500/day**", status line "🟡 Manageable"); **quote bubble** (italic + author); **typing indicator** (3 dots, neutral-500/600/700).
- **Composer** (surface, 1px divider above): row of `tag-outline` quick chips (＋ Task, ⏰ Reminder, 💰 Budget, 📰 News); input row = pill (bg background, 1px divider, 22px radius) "Type a message…" + paperclip + microphone, then 42px round accent FAB with paper-plane-right(fill, bg-colored glyph).

### Bottom Tab Bar (both screens)
Surface bg, 1px top divider, 4 equal items (icon 22px + label 10.5px): **Home** (house), **Chat** (chat-circle-dots), **Calendar** (calendar-blank), **More** (squares-four). Active item = accent color + **filled** icon variant; inactive = neutral-500 + regular icon.

## Interactions & Behavior
- Ask bar and Chat tab → Chat screen. Quick chips prefill/send a templated message to the assistant.
- Send button posts the message → backend intent classifier → feature function → renders the returned rich result as an assistant bubble. Show the typing indicator while awaiting the response.
- Task checkboxes toggle complete (calls `complete_task`). Reminder strip → Reminders detail. Shortcut tiles → their feature screens. "Lihat semua" → Tasks list.
- Budget progress bar width = free-money / total. Status color/emoji thresholds from backend (`<50k` tight, `<100k` manageable, else comfortable).
- Standard native transitions; keep the accent as line/glow, never large fills (Nocturne rule).

## State Management
- `activeTab` (Home|Chat|Calendar|More).
- Chat: `messages[]` (role, type: text|task|budget|quote|typing, payload), `draft`, `isAssistantTyping`.
- Home: `tasks[]`, `nextEvent`, `budgetSummary {remaining, deductions, free, dailyBudget, daysToPayday, statusLevel}`, `reminders[]`, `quoteOfDay`.
- Data fetching: reuse existing backend feature functions behind a REST/websocket API (get_tasks, get_events, calculate_budget, generate_daily_quote, etc.). Auth per user instead of a single YOUR_NUMBER.

## Tweakable Theme (in the prototype)
The prototype exposes three theme props (Accent color, Ground = Midnight/Deep indigo/Slate, Corner = Rounded/Crisp) implemented by overriding the CSS custom properties. In the real app, expose these as a **theme config** (accent color + surface/bg pair + radius scale) so the look stays token-driven.

## Files
- `Assistant App.dc.html` — the HTML design prototype (both screens + theme tweaks).
- `android-frame.jsx` — mockup device bezel (reference only; not for porting).
- Backend feature reference (not included here): `features/*.py`, `ai/classifier.py`, `ai/tools.py` in the `freerailwaytrial2` repo define the intents and result shapes the chat renders.

## Assets
No raster assets. Icons = Phosphor (install the platform package). Fonts = Inter (Google Fonts / bundled). No photographs used in these two screens.
