"""Two-way sync between the local budget ledger and Wallet by BudgetBakers'
REST API. See docs/BUDGETBAKERS_API.md for the vendor API reference this
package implements against.

client.py   — HTTP transport (pagination, rate-limit, 409/401/207 handling)
mapping.py  — pure snake_case<->Wallet-JSON conversions, no DB/HTTP/clock
sync.py     — orchestration: pull, push, preview, compare

Manual-trigger only (features/budget/blueprint.py's /sync/wallet/* routes)
— no scheduler job. See docs/BUDGETBAKERS_API.md's write matrix for which
entities can actually round-trip (goals and standing-orders cannot)."""
