import json
from unittest.mock import patch


def test_breakdown_returns_null_when_never_computed(client, auth_headers):
    with patch("api.state_get", return_value=None):
        resp = client.get("/api/budget/breakdown", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] is None


def test_breakdown_normalizes_snake_case_to_camel_case(client, auth_headers):
    stored = {
        "remaining": 3_254_624,
        "still_owed": [{"name": "Internet", "amount": 150_000, "due_day": None}],
        "pending_amounts": [],
        "remaining_var": [{"name": "Claude", "remaining": 0, "spent": 400_000, "over_budget": 0}],
        "unmatched_spending": [{"name": "Netflix", "amount": 120_000}],
        "total_still_owed": 150_000,
        "total_var_remaining": 0,
        "total_deductions": 150_000,
        "free_money": 3_104_624,
        "daily_budget": 155_231.2,
        "days_left": 20,
        "status_level": "comfortable",
    }
    with patch("api.state_get", return_value=json.dumps(stored)):
        resp = client.get("/api/budget/breakdown", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["stillOwed"] == [{"name": "Internet", "amount": 150_000, "dueDay": None}]
    assert data["remainingVar"] == [{"name": "Claude", "remaining": 0, "spent": 400_000, "overBudget": 0}]
    assert data["unmatchedSpending"] == [{"name": "Netflix", "amount": 120_000}]
    assert data["totalStillOwed"] == 150_000
    assert data["totalVarRemaining"] == 0
    assert data["totalDeductions"] == 150_000
    assert data["freeMoney"] == 3_104_624
    assert data["dailyBudget"] == 155_231.2
    assert data["daysLeft"] == 20
    assert data["statusLevel"] == "comfortable"
    # snake_case keys must not leak through
    assert "still_owed" not in data
    assert "daily_budget" not in data
