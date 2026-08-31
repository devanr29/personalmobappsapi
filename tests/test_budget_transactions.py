"""HTTP-level tests for the transactions CRUD routes. Uses conftest's
client/auth_headers against whatever DB_PATH/DATABASE_URL resolves to at
collection time (the real dev bot.db, absent a dedicated fixture DB) —
every row created here is torn down at the end of each test so nothing
leaks into real data."""
import pytest

from features.budget import repo


@pytest.fixture
def wallet_and_category():
    wallet = repo.create_wallet("_TestCash", opening_balance=500_000, is_default=False)
    category = repo.create_category("_TestFuel", "variable", monthly_limit=70_000)
    yield wallet, category

    conn = _teardown_conn()
    conn.execute("DELETE FROM budget_transactions WHERE wallet_id = ? OR category_id = ?", (wallet["id"], category["id"]))
    conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet["id"],))
    conn.execute("DELETE FROM budget_categories WHERE id = ?", (category["id"],))
    conn.commit()
    conn.close()


def _teardown_conn():
    from db import db_conn
    return db_conn()


def test_create_transaction_decreases_remaining_and_daily_budget_in_response(client, auth_headers, wallet_and_category):
    wallet, category = wallet_and_category

    before = client.get("/api/budget", headers=auth_headers).get_json()["data"]

    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 50_000, "direction": "expense", "categoryId": category["id"], "walletId": wallet["id"]},
    )
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    txn = body["transaction"]
    summary = body["summary"]

    assert txn["amount"] == 50_000
    assert txn["categoryName"] == "_TestFuel"
    assert txn["walletName"] == "_TestCash"

    if before is not None:
        assert summary["dailyBudget"] <= before["dailyBudget"]

    repo.soft_delete_transaction(txn["id"])


def test_create_transaction_reduces_category_remaining_in_breakdown(client, auth_headers, wallet_and_category):
    # The mobile UI's inline "log spend" input has no direct assertion that
    # a posted expense actually lands in GET /breakdown's remainingVar for
    # that category — this closes that gap end to end.
    wallet, category = wallet_and_category

    before_breakdown = client.get("/api/budget/breakdown", headers=auth_headers).get_json()["data"]
    before_free = before_breakdown["freeMoney"]

    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 50_000, "direction": "expense", "categoryId": category["id"], "walletId": wallet["id"]},
    )
    assert resp.status_code == 201
    txn_id = resp.get_json()["data"]["transaction"]["id"]

    after_breakdown = client.get("/api/budget/breakdown", headers=auth_headers).get_json()["data"]
    line = next(v for v in after_breakdown["remainingVar"] if v["categoryId"] == category["id"])
    assert line["spent"] == 50_000
    assert line["remaining"] == 20_000  # 70_000 monthly_limit - 50_000 spent
    # A spend with a walletId must not increase free money — the wallet
    # balance drop and the category's remaining drop should offset each
    # other (or, if the category was already overspent, only decrease it).
    # A spend posted without a walletId would leave money_in_hand()
    # untouched while totalVarRemaining still drops, incorrectly pushing
    # freeMoney up instead.
    assert after_breakdown["freeMoney"] <= before_free

    repo.soft_delete_transaction(txn_id)


def test_log_only_expense_hits_the_envelope_but_not_the_wallet(client, auth_headers, wallet_and_category):
    # "Log spend" with logOnly on: the money already left the wallet via a
    # transaction that was never attributed to this budget, so recording it
    # must move the category's `spent` without a second balance deduction.
    wallet, category = wallet_and_category
    balance_before = repo.wallet_balance(wallet["id"])

    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 40_000, "direction": "expense", "categoryId": category["id"], "logOnly": True},
    )
    assert resp.status_code == 201
    txn = resp.get_json()["data"]["transaction"]
    assert txn["walletId"] is None
    assert txn["walletName"] is None
    assert txn["source"] == "log_only"

    breakdown = client.get("/api/budget/breakdown", headers=auth_headers).get_json()["data"]
    line = next(v for v in breakdown["remainingVar"] if v["categoryId"] == category["id"])
    assert line["spent"] == 40_000
    assert line["remaining"] == 30_000  # 70_000 limit - 40_000

    # The wallet balance is untouched — that's the whole point: the real
    # transaction elsewhere already accounts for the outflow.
    assert repo.wallet_balance(wallet["id"]) == balance_before

    repo.soft_delete_transaction(txn["id"])


def test_log_only_rejects_income_and_missing_category(client, auth_headers, wallet_and_category):
    _, category = wallet_and_category

    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 10_000, "direction": "income", "categoryId": category["id"], "logOnly": True},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 10_000, "direction": "expense", "logOnly": True},
    )
    assert resp.status_code == 400


def test_create_transaction_rejects_unknown_category(client, auth_headers, wallet_and_category):
    wallet, _ = wallet_and_category
    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 10_000, "direction": "expense", "categoryId": 999_999, "walletId": wallet["id"]},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_transaction_requires_amount_and_direction(client, auth_headers):
    resp = client.post("/api/budget/transactions", headers=auth_headers, json={"amount": 10_000})
    assert resp.status_code == 400


def test_soft_delete_restores_category_spend(client, auth_headers, wallet_and_category):
    wallet, category = wallet_and_category
    resp = client.post(
        "/api/budget/transactions",
        headers=auth_headers,
        json={"amount": 15_000, "direction": "expense", "categoryId": category["id"], "walletId": wallet["id"]},
    )
    txn_id = resp.get_json()["data"]["transaction"]["id"]

    resp = client.delete(f"/api/budget/transactions/{txn_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["deleted"] is True

    resp = client.get(f"/api/budget/transactions?walletId={wallet['id']}", headers=auth_headers)
    ids = [t["id"] for t in resp.get_json()["data"]["items"]]
    assert txn_id not in ids


def test_delete_unknown_transaction_is_404(client, auth_headers):
    resp = client.delete("/api/budget/transactions/999999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_list_transactions_bad_limit_falls_back_instead_of_500(client, auth_headers):
    resp = client.get("/api/budget/transactions?limit=abc", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["items"] == [] or isinstance(resp.get_json()["data"]["items"], list)


def test_list_transactions_limit_is_capped(client, auth_headers):
    resp = client.get("/api/budget/transactions?limit=100000", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["meta"]["limit"] <= 200


def test_list_transactions_paginates_via_meta(client, auth_headers, wallet_and_category):
    wallet, category = wallet_and_category
    created_ids = []
    for i in range(3):
        resp = client.post(
            "/api/budget/transactions",
            headers=auth_headers,
            json={"amount": 1000 * (i + 1), "direction": "expense", "categoryId": category["id"], "walletId": wallet["id"]},
        )
        created_ids.append(resp.get_json()["data"]["transaction"]["id"])

    resp = client.get(f"/api/budget/transactions?walletId={wallet['id']}&limit=2&offset=0", headers=auth_headers)
    body = resp.get_json()
    assert len(body["data"]["items"]) == 2
    assert body["meta"]["limit"] == 2
    assert body["meta"]["hasMore"] is True

    for txn_id in created_ids:
        repo.soft_delete_transaction(txn_id)
