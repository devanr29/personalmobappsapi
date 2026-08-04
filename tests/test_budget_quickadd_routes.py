import json
from unittest.mock import patch

import pytest

from features.budget import repo


@pytest.fixture
def wallet_and_fuel_category():
    wallet = repo.create_wallet("_TestCash2", opening_balance=500_000, is_default=False)
    category = repo.create_category(
        "_TestFuel2", "variable", monthly_limit=70_000,
        keywords=json.dumps(["bensin", "pertalite", "pertamax", "bbm", "spbu"]),
    )
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


def test_parse_route_returns_parsed_shape_without_writing(client, auth_headers, wallet_and_fuel_category):
    wallet, category = wallet_and_fuel_category
    resp = client.post("/api/budget/transactions/parse", headers=auth_headers, json={"message": "beli bensin 50rb"})
    assert resp.status_code == 200
    parsed = resp.get_json()["data"]["parsed"]
    assert parsed["amount"] == 50_000
    assert parsed["categoryId"] == category["id"]
    assert parsed["source"] == "quick_regex"

    items, total = repo.get_transactions(category_id=category["id"])
    assert total == 0  # parse-only, nothing written


def test_quick_add_creates_transaction_with_zero_network_calls(client, auth_headers, wallet_and_fuel_category):
    wallet, category = wallet_and_fuel_category
    with patch("features.budget.quickadd.groq_complete") as mock_groq:
        resp = client.post(
            "/api/budget/transactions/quick",
            headers=auth_headers,
            json={"message": "beli bensin 50rb", "walletId": wallet["id"]},
        )
    mock_groq.assert_not_called()
    assert resp.status_code == 201
    body = resp.get_json()["data"]
    assert body["transaction"]["amount"] == 50_000
    assert body["transaction"]["categoryName"] == "_TestFuel2"
    assert body["parse"]["source"] == "quick_regex"


def test_quick_add_survives_llm_outage_when_amount_found_locally(client, auth_headers, wallet_and_fuel_category):
    wallet, category = wallet_and_fuel_category
    with patch("features.budget.quickadd.groq_complete", side_effect=RuntimeError("groq down")):
        resp = client.post(
            "/api/budget/transactions/quick",
            headers=auth_headers,
            json={"message": "50rb", "walletId": wallet["id"]},  # no category keyword -> triggers LLM path
        )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["transaction"]["amount"] == 50_000


def test_quick_add_with_no_amount_returns_422_with_partial(client, auth_headers, wallet_and_fuel_category):
    wallet, category = wallet_and_fuel_category
    with patch("features.budget.quickadd.groq_complete", side_effect=RuntimeError("groq down")):
        resp = client.post(
            "/api/budget/transactions/quick",
            headers=auth_headers,
            json={"message": "beli sesuatu", "walletId": wallet["id"]},
        )
    assert resp.status_code == 422
    assert "partial" in resp.get_json()["data"]
