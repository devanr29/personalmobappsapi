"""snake_case ledger/compute dicts -> camelCase API dicts. Single place for
this conversion, replacing the one-off _camel_budget_breakdown that used to
live in api.py."""
from features.budget import repo


def camel_wallet(w: dict) -> dict:
    return {
        "id": w["id"], "name": w["name"], "kind": w["kind"],
        "openingBalance": w["opening_balance"], "spendable": w["spendable"],
        "isDefault": w["is_default"], "archived": w["archived"],
    }


def camel_category(c: dict) -> dict:
    return {
        "id": c["id"], "name": c["name"], "kind": c["kind"],
        "monthlyLimit": c["monthly_limit"], "rollover": c["rollover"],
        "archived": c["archived"],
    }


def camel_bill(b: dict) -> dict:
    return {
        "id": b["id"], "name": b["name"], "amount": b["amount"],
        "dueDay": b["due_day"], "cadence": b["cadence"], "active": b["active"],
        "categoryId": b["category_id"], "walletId": b["wallet_id"], "autopost": b["autopost"],
    }


def camel_transaction(t: dict) -> dict:
    # repo.get_transactions() (list queries) already joins these in; only
    # the single-row create/update/delete paths need the extra lookups —
    # 2 queries there is fine, it's the 50-row list that made the N+1 hurt.
    if "category_name" in t:
        category_name = t["category_name"]
    else:
        category = repo.get_category(t["category_id"]) if t["category_id"] is not None else None
        category_name = category["name"] if category else None
    if "wallet_name" in t:
        wallet_name = t["wallet_name"]
    else:
        wallet = repo.get_wallet(t["wallet_id"]) if t["wallet_id"] is not None else None
        wallet_name = wallet["name"] if wallet else None
    return {
        "id": t["id"],
        "occurredAt": t["occurred_at"],
        "amount": t["amount"],
        "direction": t["direction"],
        "categoryId": t["category_id"],
        "categoryName": category_name,
        "walletId": t["wallet_id"],
        "walletName": wallet_name,
        "note": t["note"],
        "source": t["source"],
        "billId": t["bill_id"],
        "goalId": t["goal_id"],
    }


def camel_goal(g: dict) -> dict:
    return {
        "id": g["id"], "name": g["name"], "kind": g["kind"], "targetAmount": g["target_amount"],
        "targetDate": g["target_date"], "monthlyContribution": g["monthly_contribution"],
        "reserveFromFree": g["reserve_from_free"], "walletId": g["wallet_id"], "archived": g["archived"],
    }


def camel_seed_result(result: dict) -> dict:
    return {
        "wallets": [camel_wallet(w) for w in result["wallets"]],
        "categories": [camel_category(c) for c in result["categories"]],
        "bills": [camel_bill(b) for b in result["bills"]],
        "periodId": result["periodId"],
        "openingBalance": result["openingBalance"],
    }


def camel_budget_breakdown(data: dict) -> dict:
    return {
        "remaining": data["remaining"],
        "stillOwed": [
            {"name": e["name"], "amount": e["amount"], "dueDay": e.get("due_day")} for e in data["still_owed"]
        ],
        "pendingAmounts": [
            {"name": e["name"], "amount": e["amount"], "dueDay": e.get("due_day")} for e in data["pending_amounts"]
        ],
        "remainingVar": [
            {"name": v["name"], "remaining": v["remaining"], "spent": v["spent"], "overBudget": v["over_budget"]}
            for v in data["remaining_var"]
        ],
        "unmatchedSpending": [{"name": u["name"], "amount": u["amount"]} for u in data["unmatched_spending"]],
        "totalStillOwed": data["total_still_owed"],
        "totalVarRemaining": data["total_var_remaining"],
        "totalDeductions": data["total_deductions"],
        "freeMoney": data["free_money"],
        "dailyBudget": int(data["daily_budget"]),
        "daysLeft": data["days_left"],
        "statusLevel": data["status_level"],
    }
