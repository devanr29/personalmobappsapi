# Wallet by BudgetBakers — REST API reference

Notes from the vendor's BETA REST API (v1.5.0), captured 2026-08-10 for the sync integration
in `features/budget/wallet/`. Source: `https://rest.budgetbakers.com/wallet/reference` and the
OpenAPI spec at `https://rest.budgetbakers.com/wallet/openapi`. Since it's BETA, re-check the
live spec before relying on anything below for a change.

## Base URL & auth

```
https://rest.budgetbakers.com/wallet
Authorization: Bearer <token>
```

Tokens are personal JWTs minted in the Wallet web app (Settings → REST API, Premium plan
required). **90-day expiry.** Ours was minted 2026-08-10 and expires **2026-11-08** — the sync
status endpoint should surface this so it doesn't fail silently as a 401 three months from now.

A Wallet MCP server also exists at `https://mcp.wallet.budgetbakers.com` (OAuth or MCP token) for
conversational access from Claude/ChatGPT — not used here, but worth remembering if `ai/chat.py`
ever wants to answer questions against Wallet data directly instead of through the synced copy.

## Resource write matrix

This is the constraint that shapes the whole integration — several resources are pull-only.

| Resource | GET | POST | PATCH | DELETE |
|---|---|---|---|---|
| `records` | ✅ | ✅ (batch ≤20) | ✅ (batch ≤10) | ✅ (batch ≤10, via `DELETE /v1/api/records`) |
| `accounts` | ✅ | ✅ (single) | ✅ (batch ≤10) | ❌ not supported via API |
| `budgets` | ✅ | ✅ (single) | ✅ (batch ≤10) | ✅ (no restrictions) |
| `categories` | ✅ | custom only (single, via `/categories/custom`) | ✅ (batch ≤10) | custom only |
| `labels` | ✅ | ✅ (single) | ✅ (batch) | ❌ not supported via API |
| `goals` | ✅ | ❌ | ❌ | ❌ not supported via API |
| `standing-orders` (+ `/items`) | ✅ | ❌ | ❌ | ✅ |
| `record-rules` | ✅ | ❌ | ❌ | ✅ |

**Goals and standing orders can only ever flow Wallet → local.** There is no API to create or
edit them — this is a vendor limitation, not a design choice on our end.

## Pagination

`limit` (default 30, max 200) + `offset`. Response includes `nextOffset` when more results
exist. A full backfill of the per-user cap (20,000 records) at `limit=200` is ~100 requests.

## Filter grammar

Query params take a `prefix.value` filter on top of the field name.

**Text fields** (`note`, `payee`/`counterParty`): `eq.`, `contains.` (case-sensitive),
`contains-i.` (case-insensitive). Up to 2 repeated params = AND.

**Numeric/datetime fields** (`amount`, `recordDate`, `createdAt`, `updatedAt`): `eq.`, `gt.`,
`gte.`, `lt.`, `lte.`. Up to 2 conditions = AND, e.g. `amount=gte.100&amount=lte.500`, or
comma-separated `amount=gte.100,lte.500`.

Date-only values get whole-day UTC semantics — `lte.2025-01-15` means "up to and including
Jan 15", i.e. `lt.2025-01-16T00:00:00Z` under the hood.

`updatedAt=gte.<cursor>` is the handle for incremental pull sync.

## Rate limiting

Token-bucket, **300 requests/hour** per client. Headers on every response:

```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 487
```

429 on exhaustion. The client (`wallet/client.py`) checks `X-RateLimit-Remaining` after each call
and aborts the run with partial progress rather than eating a 429.

## Data sync semantics

**Initial sync**: begins the moment the first API token is generated. Until it completes, every
request returns **409**:

```json
{"error": "init_sync_in_progress", "message": "Data synchronization in progress. Please retry later.", "retry_after_minutes": 5}
```

**Ongoing sync**: after that, data is always returned but may lag the mobile/web apps slightly.
Response headers:

| Header | Meaning |
|---|---|
| `X-Last-Data-Change-At` | timestamp of the last data modification |
| `X-Last-Data-Change-Rev` | revision counter — compare across calls to cheaply detect "anything changed?" |
| `X-Sync-In-Progress` | `true` = more changes may still be landing |

## Agent hints

Add `agentHints=true` to any request to get structured advisory info back — pagination has-more,
partial ID-match results, empty-result notices, inferred date bounds, rate-limit warnings. Aimed
at LLM agents driving the API; relevant if we ever point `ai/chat.py` at Wallet directly.

## Batch writes: not atomic, HTTP 207 on partial success

Every write endpoint that accepts arrays processes items **independently**. If all succeed: 200.
If some fail: **207**, body shaped like:

```json
{
  "summary": {"total": 5, "succeeded": 3, "clientErrors": 1, "serverErrors": 1},
  "results": [{"success": true, ...}, {"success": false, "error": "...", "errorType": "client_error"}]
}
```

`validation=strict` on PATCH forces fail-fast instead of best-effort partial processing.

## Records

**Create** — `POST /v1/api/records`, ≤20/request, ≤20,000/user total (mobile+web+API combined).

| Field | Required | Notes |
|---|---|---|
| `accountId` | yes | must exist, cannot be bank-synced |
| `amount` | yes | `DECIMAL(19,2)`, non-zero. Negative = expense, positive = income. `recordType` auto-derived from sign |
| `recordDate` | yes | ISO 8601; ≤24h future, ≤10y past |
| `paymentType` | yes | `cash \| debit_card \| credit_card \| transfer \| voucher \| mobile_payment \| web_payment` |
| `categoryId` | no | any category UUID; omitted → auto "Unknown Income/Expense"; system categories forbidden |
| `recordState` | no | default `cleared`; also `reconciled`, `uncleared` |
| `labelIds` | no | array of label UUIDs |
| `note` | no | ≤255 chars |
| `counterParty` | no | ≤255 chars |

Transfers use a `transfer` object with `pairingMode`: `"new"` (creates linked mirror on target
account), `"existing"` (pairs to an existing record), `"unpaired"`. Re-pairing an already-paired
target orphans its old partner automatically.

**Patch** — `PATCH /v1/api/records`, ≤10/request, ≥1 field required.

`categoryId`, `labelIds` (replace-all, `[]` clears), `note`, `counterParty`, `paymentType` are
freely patchable. `recordState`, `recordDate`, `amount` are **locked on bank-synced records**
(client_error if attempted) — `amount` is always interpreted in the account's currency regardless
of the record's original currency; `refAmount` recalculates automatically. `accountId` can move a
record between two non-bank-synced accounts of the same currency. On a transfer record,
`categoryId` is locked (system "Transfer" category) — clear transfer state first with
`$clear:["transfer"]`. **`uncleared` bank-synced records cannot be touched at all** — the
transaction hasn't settled and the bank feed may overwrite any edit.

## Accounts

**Create** — `POST /v1/api/accounts`, single item, ≤50/user.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | ≤80 chars |
| `accountType` | yes | writable: `General, Cash, CurrentAccount, SavingAccount, Insurance`. Read-only (mobile-managed): `CreditCard, Investment, Loan`, etc. |
| `currencyCode` | yes | ISO 4217, immutable after creation |
| `initialBalance` | yes | `DECIMAL(19,2)` |
| `color` | no | one of 16, random if omitted |

**Patch** — ≤10/request: `name`, `archived`, `color`, `initialBalance` (also recalcs base-currency
amount), `excludeFromStats`, `bankAccountNumber`. `accountType`/`currencyCode` immutable.
**Bank-synced accounts cannot be patched via API at all.**

No delete via API. `DELETE /v1/api/accounts?id=...` in the spec's delete-entities table is listed
as **not supported** for accounts specifically — check references first regardless via
`GET /accounts/references?id=...`.

## Categories

Custom categories always derive from a system (base) category via `parentId` — for narrow
sub-buckets, e.g. "Subscriptions" under "Entertainment".

**Create** — `POST /v1/api/categories/custom`, single, ≤50 custom/user.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | ≤80, unique case-insensitive across ALL categories |
| `parentId` | yes | UUID of a system category; internal ones forbidden (see below) |
| `color` | no | defaults to parent's |
| `cardinality` | no | `none \| must \| need \| want`, defaults to parent's |

**Restricted system categories** — cannot be assigned to records or used as `parentId`:

| Name | UUID |
|---|---|
| Debt | `5c5c4e20-00c8-8000-8000-000000000000` |
| Transfer | `5c5c4e21-00c8-8000-8000-000000000000` |
| Shopping List | `5c5c4e22-00c8-8000-8000-000000000000` |
| Uncategorized | `5c5c4e23-00c8-8000-8000-000000000000` |

**Patch** — ≤10/request, works on base or custom: `name` (sets `customName:true`, mutually
exclusive with `resetName`), `resetName` (base categories only), `color`, `cardinality`.

**Delete** — custom only, must have zero references (records/budgets/standing-orders/rules);
pre-check with `GET /categories/references?id=...`.

## Budgets

Vendor "budgets" are calendar-anchored, not pay-cycle anchored — **this cannot express our
25th→24th recurring period**, so `budget_periods` never syncs against this resource. We only use
`GET /budgets?spending=current+N` as a rough cross-check figure, not as a write target.

**Create** — `POST /v1/api/budgets`, single, ≤50/user.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | ≤80 |
| `currencyCode` | yes | immutable |
| `type` | yes | `BUDGET_INTERVAL_WEEK \| BUDGET_INTERVAL_MONTH \| BUDGET_INTERVAL_YEAR \| BUDGET_CUSTOM`, immutable |
| `limit` | yes | `DECIMAL(19,2)`, > 0 |
| `startDate`/`endDate` | `BUDGET_CUSTOM` only | `YYYY-MM-DD`, `endDate ≥ startDate` |
| `categoryIds` / `accountIds` / `labelIds` | no | empty = track everything |

`GET /budgets?spending=current+N` (N ∈ {0,2,5,10,25} past periods) returns computed
`spent/remaining/progress/overspent/effectiveLimit/recordCount` per period — Wallet's own budget
math, comparable to (but never period-aligned with) `features/budget/compute.py`.

**Patch**: `resetLimit` (clears all overrides, sets uniform baseline — combinable with
`limitOverrides`, reset applies first), `limitOverrides` (≤50, per-period, not allowed on
`BUDGET_CUSTOM`), `accountIds`/`categoryIds`/`labelIds` (array = replace-all, `{add,remove}` =
partial), `closed` (bool, auto-stamps `closedDate`). `type`/`currencyCode` immutable.

**Delete**: always allowed — budgets have no child references.

## Deleting entities

`DELETE /v1/api/{type}` — up to 10 IDs per request.

| Type | Deletable | Restrictions |
|---|---|---|
| `records` | yes | not bank-synced; transfer pairs must be in the same batch; no active standing-order reference |
| `budgets` | yes | none |
| `standing-orders` | yes | none |
| `record-rules` | yes | none |
| `categories` | custom only | must have zero references |
| `accounts` / `labels` / `goals` | **no** | not supported via API at all |

Pre-check: `GET /v1/api/{type}/references?id=uuid1,uuid2` (≤10 IDs) — shows which entities
reference the given IDs before you attempt a delete.

## Entity ↔ local schema mapping

| Wallet | Local (`features/budget/schema.py`) | Notes |
|---|---|---|
| `records` (UUID) | `budget_transactions` (int PK) | sign→`direction`, `convertedAmount.value`(→IDR)→int `amount`, `recordDate`↔`occurred_at`, transfer pair↔single row+`transfer_wallet_id` |
| `accounts` | `budget_wallets` | `accountType`↔`kind`, `initialBalance`↔`opening_balance` |
| `categories` (system+custom) | `budget_wallet_category_names` (display cache only) | id→name only, refreshed every pull; **not** `budget_categories` — that pull (with `cardinality`↔`kind`) was removed 2026-08-31 for creating ~85 inert categories (see `features/budget/wallet/sync.py`'s module docstring) |
| `labels` | `budget_labels` (new) | flat, no equivalent existed locally before this integration |
| `goals` | `budget_goals` | pull-only; `state active/paused/reached`→`archived` |
| `standing-orders`+`/items` | `budget_bills`+`budget_bill_payments` | pull-only; RRULE→`cadence`+`due_day` |
| `budgets` (spending figures only) | — (compare-only, `compute.py`) | never written; periods don't align |
| — | `budget_periods` | Wallet has no equivalent — pay-cycle stays 100% local |

Linkage between the two ID spaces (int ↔ UUID) lives in the new `budget_wallet_links` table
(migration 2), not embedded in the entity tables themselves — keeps the core schema vendor-agnostic
if Wallet is ever swapped out or dropped, same rationale as `budget_alert_log` staying separate
from `budget_transactions`.

## What's worth stealing for our own `/api/budget`

Independent of the sync integration, several of Wallet's API conventions are worth adopting on our
own budget blueprint:

- **Filter prefixes** (`amount=gte.100`, `note=contains-i.grocery`) — more expressive than our
  current flat `?categoryId=&walletId=&direction=&from=&to=` on `GET /transactions`.
- **`withTotal`** — optional total-count param instead of always paying for a count query.
- **Batch writes with HTTP 207** — our `PATCH/DELETE` are all single-item today; batch would help
  the mobile bulk-edit case.
- **`GET /{type}/references?id=...`** pre-check before delete — we currently just let FK
  `ON DELETE SET NULL`/`CASCADE` silently absorb it; an explicit pre-check surfaces "this bill has
  3 payments" to the user before they delete.
- **`agentHints=true`** — directly relevant to `ai/chat.py`'s budget intents; a hints array
  (pagination/partial-match/rate-limit) is a nice pattern for an LLM-facing endpoint even without a
  literal rate limit to warn about.
- **`cardinality` (`must/need/want`)** — richer than our binary `fixed/variable` `kind`, though
  changing that is a bigger migration than it's worth right now.
