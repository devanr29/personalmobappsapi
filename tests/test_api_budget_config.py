from unittest.mock import patch


def test_get_budget_config_returns_camel_case(client, auth_headers):
    fixed = [{"name": "Internet", "amount": 150_000, "due_day": None}]
    variable = [{"name": "Claude", "budget": 400_000}]
    with patch("api.get_fixed_expenses", return_value=fixed), \
         patch("api.get_variable_budgets", return_value=variable):
        resp = client.get("/api/budget/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["fixedExpenses"] == [{"name": "Internet", "amount": 150_000, "dueDay": None}]
    assert data["variableBudgets"] == [{"name": "Claude", "budget": 400_000}]


def test_add_fixed_expense_requires_name_and_amount(client, auth_headers):
    resp = client.post("/api/budget/config/fixed", headers=auth_headers, json={"name": "Gym"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_add_fixed_expense_success(client, auth_headers):
    with patch("api.add_fixed_expense", return_value="✅ Fixed expense *Gym* — Rp 200.000 added.") as mock_add:
        resp = client.post("/api/budget/config/fixed", headers=auth_headers, json={"name": "Gym", "amount": 200000, "dueDay": 1})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"created": True}
    mock_add.assert_called_once_with("Gym", 200000, 1)


def test_add_fixed_expense_failure_is_internal_error(client, auth_headers):
    with patch("api.add_fixed_expense", return_value="⚠️ Could not add fixed expense: boom"):
        resp = client.post("/api/budget/config/fixed", headers=auth_headers, json={"name": "Gym", "amount": 200000})
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "INTERNAL_ERROR"


def test_edit_fixed_expense_not_found(client, auth_headers):
    with patch("api.edit_fixed_expense", return_value="❌ No fixed expense matching *Gym* found."):
        resp = client.patch("/api/budget/config/fixed/Gym", headers=auth_headers, json={"newAmount": 250000})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_edit_fixed_expense_omitted_due_day_passes_ellipsis(client, auth_headers):
    # Omitting newDueDay entirely must mean "leave it unchanged" (Python
    # Ellipsis sentinel), distinct from explicitly sending newDueDay: null
    # ("clear it") — both are valid client intents and must not collapse
    # to the same call.
    with patch("api.edit_fixed_expense", return_value="✏️ Fixed expense updated: *Gym* — Rp 250.000.") as mock_edit:
        resp = client.patch("/api/budget/config/fixed/Gym", headers=auth_headers, json={"newAmount": 250000})
    assert resp.status_code == 200
    _, kwargs = mock_edit.call_args
    assert kwargs["new_due_day"] is ...


def test_edit_fixed_expense_explicit_null_due_day_clears_it(client, auth_headers):
    with patch("api.edit_fixed_expense", return_value="✏️ Fixed expense updated: *Gym* — Rp 250.000.") as mock_edit:
        resp = client.patch("/api/budget/config/fixed/Gym", headers=auth_headers, json={"newDueDay": None})
    assert resp.status_code == 200
    _, kwargs = mock_edit.call_args
    assert kwargs["new_due_day"] is None


def test_delete_fixed_expense_success(client, auth_headers):
    with patch("api.remove_fixed_expense", return_value="🗑️ Fixed expense *Gym* removed."):
        resp = client.delete("/api/budget/config/fixed/Gym", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"name": "Gym", "deleted": True}


def test_delete_fixed_expense_not_found(client, auth_headers):
    with patch("api.remove_fixed_expense", return_value="❌ No fixed expense matching *Gym* found."):
        resp = client.delete("/api/budget/config/fixed/Gym", headers=auth_headers)
    assert resp.status_code == 404


def test_add_variable_budget_success(client, auth_headers):
    with patch("api.add_variable_budget", return_value="✅ Variable budget *Coffee* — Rp 100.000 added.") as mock_add:
        resp = client.post("/api/budget/config/variable", headers=auth_headers, json={"name": "Coffee", "budget": 100000})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"created": True}
    mock_add.assert_called_once_with("Coffee", 100000)


def test_delete_variable_budget_success(client, auth_headers):
    with patch("api.remove_variable_budget", return_value="🗑️ Variable budget *Coffee* removed."):
        resp = client.delete("/api/budget/config/variable/Coffee", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"name": "Coffee", "deleted": True}
