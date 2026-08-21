"""HTTP-level smoke tests for the Phase 4 CRUD routes — wallets, categories,
bills, transfer, reconcile, setup status. Confirms the routes are wired and
marshal correctly; the underlying behavior is covered in depth by the
service-level tests (test_budget_{wallets,categories,bills,setup}.py).
Runs against the real dev bot.db like test_budget_transactions.py, cleaning
up every row it creates."""
from features.budget import repo


def _teardown_conn():
    from db import db_conn
    return db_conn()


def test_wallet_crud_routes(client, auth_headers):
    resp = client.post("/api/budget/wallets", headers=auth_headers, json={"name": "_HttpWallet", "openingBalance": 10_000})
    assert resp.status_code == 201
    wallet = resp.get_json()["data"]["wallet"]
    assert wallet["balance"] == 10_000

    resp = client.patch(f"/api/budget/wallets/{wallet['id']}", headers=auth_headers, json={"name": "_HttpWalletRenamed"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["wallet"]["name"] == "_HttpWalletRenamed"

    resp = client.delete(f"/api/budget/wallets/{wallet['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert repo.get_wallet(wallet["id"]) is None


def test_category_crud_routes(client, auth_headers):
    resp = client.post(
        "/api/budget/categories", headers=auth_headers,
        json={"name": "_HttpCategory", "kind": "variable", "monthlyLimit": 50_000},
    )
    assert resp.status_code == 201
    category = resp.get_json()["data"]["category"]

    resp = client.patch(f"/api/budget/categories/{category['id']}", headers=auth_headers, json={"monthlyLimit": 60_000})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["category"]["monthlyLimit"] == 60_000

    resp = client.delete(f"/api/budget/categories/{category['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert repo.get_category(category["id"]) is None


def test_category_delete_in_use_is_409(client, auth_headers):
    category = repo.create_category("_HttpCategoryInUse", "variable", monthly_limit=10_000)
    txn = repo.create_transaction(1_000, "expense", category_id=category["id"])
    try:
        resp = client.delete(f"/api/budget/categories/{category['id']}", headers=auth_headers)
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "CONFLICT"
    finally:
        repo.soft_delete_transaction(txn["id"])
        conn = _teardown_conn()
        conn.execute("DELETE FROM budget_transactions WHERE id = ?", (txn["id"],))
        conn.execute("DELETE FROM budget_categories WHERE id = ?", (category["id"],))
        conn.commit()
        conn.close()


def test_bill_pay_and_unpay_routes(client, auth_headers):
    wallet = repo.create_wallet("_HttpBillWallet", opening_balance=500_000, is_default=False)
    bill = repo.create_bill("_HttpBill", 50_000, wallet_id=wallet["id"])
    try:
        resp = client.post(f"/api/budget/bills/{bill['id']}/pay", headers=auth_headers, json={})
        assert resp.status_code == 201
        txn_id = resp.get_json()["data"]["transaction"]["id"]

        resp = client.post(f"/api/budget/bills/{bill['id']}/pay", headers=auth_headers, json={})
        assert resp.status_code == 409

        resp = client.delete(f"/api/budget/bills/{bill['id']}/pay", headers=auth_headers)
        assert resp.status_code == 200

        assert repo.get_transaction(txn_id)["deleted_at"] is not None
    finally:
        conn = _teardown_conn()
        conn.execute("DELETE FROM budget_bill_payments WHERE bill_id = ?", (bill["id"],))
        conn.execute("DELETE FROM budget_transactions WHERE bill_id = ?", (bill["id"],))
        conn.execute("DELETE FROM budget_bills WHERE id = ?", (bill["id"],))
        conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet["id"],))
        conn.commit()
        conn.close()


def test_category_pay_and_unpay_routes(client, auth_headers):
    wallet = repo.create_wallet("_HttpCategoryWallet", opening_balance=500_000, is_default=False)
    category = repo.create_category("_HttpCategoryPay", "variable", monthly_limit=50_000)
    try:
        resp = client.post(
            f"/api/budget/categories/{category['id']}/pay", headers=auth_headers,
            json={"walletId": wallet["id"]},
        )
        assert resp.status_code == 201
        txn_id = resp.get_json()["data"]["transaction"]["id"]

        resp = client.post(
            f"/api/budget/categories/{category['id']}/pay", headers=auth_headers,
            json={"walletId": wallet["id"]},
        )
        assert resp.status_code == 409

        resp = client.delete(f"/api/budget/categories/{category['id']}/pay", headers=auth_headers)
        assert resp.status_code == 200

        assert repo.get_transaction(txn_id)["deleted_at"] is not None
    finally:
        conn = _teardown_conn()
        conn.execute("DELETE FROM budget_category_payments WHERE category_id = ?", (category["id"],))
        conn.execute("DELETE FROM budget_transactions WHERE category_id = ?", (category["id"],))
        conn.execute("DELETE FROM budget_categories WHERE id = ?", (category["id"],))
        conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet["id"],))
        conn.commit()
        conn.close()


def test_category_pay_without_transaction_route(client, auth_headers):
    category = repo.create_category("_HttpCategoryPayNoTxn", "variable", monthly_limit=50_000)
    try:
        resp = client.post(
            f"/api/budget/categories/{category['id']}/pay", headers=auth_headers,
            json={"createTransaction": False},
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["transaction"] is None

        items, total = repo.get_transactions(category_id=category["id"])
        assert total == 0
    finally:
        conn = _teardown_conn()
        conn.execute("DELETE FROM budget_category_payments WHERE category_id = ?", (category["id"],))
        conn.execute("DELETE FROM budget_categories WHERE id = ?", (category["id"],))
        conn.commit()
        conn.close()


def test_wallet_transfer_route(client, auth_headers):
    from_wallet = repo.create_wallet("_HttpTransferFrom", opening_balance=100_000)
    to_wallet = repo.create_wallet("_HttpTransferTo", opening_balance=0)
    try:
        resp = client.post(
            "/api/budget/wallets/transfer", headers=auth_headers,
            json={"fromWalletId": from_wallet["id"], "toWalletId": to_wallet["id"], "amount": 30_000},
        )
        assert resp.status_code == 201
        assert repo.wallet_balance(from_wallet["id"]) == 70_000
        assert repo.wallet_balance(to_wallet["id"]) == 30_000
    finally:
        conn = _teardown_conn()
        conn.execute(
            "DELETE FROM budget_transactions WHERE wallet_id IN (?, ?) OR transfer_wallet_id IN (?, ?)",
            (from_wallet["id"], to_wallet["id"], from_wallet["id"], to_wallet["id"]),
        )
        conn.execute("DELETE FROM budget_wallets WHERE id IN (?, ?)", (from_wallet["id"], to_wallet["id"]))
        conn.commit()
        conn.close()


def test_wallet_reconcile_route(client, auth_headers):
    wallet = repo.create_wallet("_HttpReconcile", opening_balance=100_000)
    try:
        resp = client.post(
            f"/api/budget/wallets/{wallet['id']}/reconcile", headers=auth_headers,
            json={"actualBalance": 120_000},
        )
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert body["adjusted"] is True
        assert body["delta"] == 20_000
    finally:
        conn = _teardown_conn()
        conn.execute("DELETE FROM budget_transactions WHERE wallet_id = ?", (wallet["id"],))
        conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet["id"],))
        conn.commit()
        conn.close()


def test_setup_status_route(client, auth_headers):
    resp = client.get("/api/budget/setup/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "seeded" in body
    assert "walletCount" in body


def test_insights_route_shape(client, auth_headers):
    resp = client.get("/api/budget/insights", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    if body is not None:
        for key in ("period", "daily", "pace", "categories", "categoriesTop", "budgetVsActual", "stats", "heatmap", "wallets"):
            assert key in body


def test_insights_history_route_shape(client, auth_headers):
    resp = client.get("/api/budget/insights/history?periods=3", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "periods" in body
    assert "spendTrend" in body
    if body["periods"]:
        assert "shortLabel" in body["periods"][0]


def test_insights_history_bad_group_by_is_400(client, auth_headers):
    resp = client.get("/api/budget/insights/history?groupBy=nonsense", headers=auth_headers)
    assert resp.status_code == 400


def test_insights_history_periods_is_clamped(client, auth_headers):
    # ?periods=9999 must not turn into an unbounded SQL LIMIT / payload.
    resp = client.get("/api/budget/insights/history?periods=9999", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["periods"]) <= 24


def test_insights_history_negative_periods_does_not_error(client, auth_headers):
    # A bare negative LIMIT is "no limit" on SQLite but a hard 22023 error
    # on Postgres -- this must never reach the database unclamped.
    resp = client.get("/api/budget/insights/history?periods=-1", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["periods"]) <= 24


def test_insights_categories_route_shape(client, auth_headers):
    resp = client.get("/api/budget/insights/categories?months=3", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    for key in ("months", "monthLabels", "windowMonths", "completeMonths", "currentMonth", "dormantCount", "categories"):
        assert key in body
    assert len(body["months"]) == 3


def test_insights_categories_months_is_clamped(client, auth_headers):
    resp = client.get("/api/budget/insights/categories?months=9999", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["months"]) <= 24


def test_insights_categories_negative_months_does_not_error(client, auth_headers):
    resp = client.get("/api/budget/insights/categories?months=-1", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["months"]) >= 1


def test_breakdown_includes_today_block(client, auth_headers):
    resp = client.get("/api/budget/breakdown", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    if body is not None:
        assert "today" in body


def test_goal_crud_and_contribute_routes(client, auth_headers):
    wallet = repo.create_wallet("_HttpGoalWallet", opening_balance=500_000, is_default=False)
    try:
        resp = client.post(
            "/api/budget/goals", headers=auth_headers,
            json={"name": "_HttpGoal", "targetAmount": 1_000_000, "monthlyContribution": 100_000},
        )
        assert resp.status_code == 201
        goal = resp.get_json()["data"]["goal"]
        assert goal["saved"] == 0

        resp = client.get("/api/budget/goals", headers=auth_headers)
        assert any(g["id"] == goal["id"] for g in resp.get_json()["data"]["items"])

        resp = client.post(
            f"/api/budget/goals/{goal['id']}/contribute", headers=auth_headers,
            json={"amount": 50_000, "walletId": wallet["id"]},
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["goal"]["saved"] == 50_000

        resp = client.delete(f"/api/budget/goals/{goal['id']}", headers=auth_headers)
        assert resp.status_code == 409  # has a contribution
    finally:
        conn = _teardown_conn()
        row = conn.execute("SELECT id FROM budget_goals WHERE name = '_HttpGoal'").fetchone()
        if row:
            conn.execute("DELETE FROM budget_goal_contributions WHERE goal_id = ?", (row[0],))
            conn.execute("DELETE FROM budget_transactions WHERE goal_id = ?", (row[0],))
            conn.execute("DELETE FROM budget_goals WHERE id = ?", (row[0],))
        conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet["id"],))
        conn.commit()
        conn.close()


def test_alerts_list_and_prefs_routes(client, auth_headers):
    resp = client.get("/api/budget/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "items" in body["data"]
    assert "unreadCount" in body["meta"]

    resp = client.get("/api/budget/alerts/prefs", headers=auth_headers)
    assert resp.status_code == 200
    prefs = resp.get_json()["data"]
    assert "dailyCheckinEnabled" in prefs

    resp = client.patch("/api/budget/alerts/prefs", headers=auth_headers, json={"overBudgetThresholdPct": 90})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["overBudgetThresholdPct"] == 90

    # restore default so this test is repeatable
    client.patch("/api/budget/alerts/prefs", headers=auth_headers, json={"overBudgetThresholdPct": 80})


def test_alerts_mark_read_route(client, auth_headers):
    resp = client.post("/api/budget/alerts/999999/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["read"] is True
