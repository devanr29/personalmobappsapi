import pytest

from features.budget.wallet import mapping


# ================================================================
# amounts / direction
# ================================================================
def test_record_amount_idr_requires_converted_amount():
    with pytest.raises(ValueError):
        mapping.record_amount_idr({"id": "r1", "amount": 1000})


def test_record_amount_idr_rounds_converted_value():
    record = {"id": "r1", "convertedAmount": {"value": 12345.6}}
    assert mapping.record_amount_idr(record) == 12346


def test_record_direction_from_negative_amount_is_expense():
    record = {"convertedAmount": {"value": -50000}}
    assert mapping.record_direction(record) == "expense"


def test_record_direction_from_positive_amount_is_income():
    record = {"convertedAmount": {"value": 50000}}
    assert mapping.record_direction(record) == "income"


def test_record_to_transaction_fields_amount_is_always_positive():
    record = {"id": "r1", "convertedAmount": {"value": -75000}, "recordDate": "2026-08-01T10:30:00Z", "note": "Coffee"}
    fields = mapping.record_to_transaction_fields(record, category_id=5, wallet_id=1)
    assert fields["amount"] == 75000
    assert fields["direction"] == "expense"
    assert fields["occurred_at"] == "2026-08-01 10:30"
    assert fields["wallet_id"] == 1
    assert fields["category_id"] == 5
    assert fields["source"] == "wallet"
    assert fields["raw_input"] == "r1"


def test_record_to_transaction_fields_transfer_wallet_id_forces_transfer_direction():
    record = {"id": "r1", "convertedAmount": {"value": -20000}, "recordDate": "2026-08-01T00:00:00Z"}
    fields = mapping.record_to_transaction_fields(record, wallet_id=1, transfer_wallet_id=2)
    assert fields["direction"] == "transfer"
    assert fields["amount"] == 20000


# ================================================================
# embeds — bare id string or {"id": ...} object
# ================================================================
def test_record_category_id_accepts_bare_string():
    assert mapping.record_category_id({"category": "cat-123"}) == "cat-123"


def test_record_category_id_accepts_embed_object():
    assert mapping.record_category_id({"category": {"id": "cat-123", "name": "Food"}}) == "cat-123"


def test_record_category_id_none_when_absent():
    assert mapping.record_category_id({}) is None


def test_record_label_ids_filters_and_extracts():
    record = {"labels": [{"id": "l1"}, "l2", None]}
    assert mapping.record_label_ids(record) == ["l1", "l2"]


def test_record_label_ids_empty_when_absent():
    assert mapping.record_label_ids({}) == []


# ================================================================
# restricted categories
# ================================================================
def test_transfer_category_is_restricted():
    assert mapping.is_restricted_category(mapping.WALLET_TRANSFER_CATEGORY_ID) is True


def test_arbitrary_category_is_not_restricted():
    assert mapping.is_restricted_category("some-other-uuid") is False


# ================================================================
# accounts <-> wallets
# ================================================================
def test_account_to_wallet_fields_maps_kind_and_balance():
    account = {"name": "BCA", "accountType": "CurrentAccount", "initialBalance": 1500000, "excludeFromStats": False, "archived": False}
    fields = mapping.account_to_wallet_fields(account)
    assert fields["kind"] == "bank"
    assert fields["opening_balance"] == 1500000
    assert fields["spendable"] is True
    assert fields["archived"] is False


def test_account_to_wallet_fields_unknown_type_defaults_to_cash():
    fields = mapping.account_to_wallet_fields({"name": "X", "accountType": "SomethingNew"})
    assert fields["kind"] == "cash"


def test_account_to_wallet_fields_reads_nested_balance_initial():
    # Live API shape (2026-08-12): no top-level initialBalance at all —
    # opening balance is nested under balance.initial.
    account = {"name": "BCA", "accountType": "Cash", "balance": {"initial": 3496982.39, "currencyCode": "IDR"}}
    fields = mapping.account_to_wallet_fields(account)
    assert fields["opening_balance"] == 3496982


def test_account_to_wallet_fields_missing_balance_defaults_to_zero():
    fields = mapping.account_to_wallet_fields({"name": "X", "accountType": "Cash"})
    assert fields["opening_balance"] == 0


def test_wallet_to_account_payload_is_always_idr():
    wallet = {"name": "Cash", "kind": "cash", "opening_balance": 100000}
    payload = mapping.wallet_to_account_payload(wallet)
    assert payload["currencyCode"] == "IDR"
    assert payload["accountType"] == "Cash"
    assert payload["initialBalance"] == 100000


# ================================================================
# categories
# ================================================================
def test_category_to_local_fields_must_and_need_become_fixed():
    assert mapping.category_to_local_fields({"name": "Rent", "cardinality": "must"})["kind"] == "fixed"
    assert mapping.category_to_local_fields({"name": "Insurance", "cardinality": "need"})["kind"] == "fixed"


def test_category_to_local_fields_want_becomes_variable():
    assert mapping.category_to_local_fields({"name": "Games", "cardinality": "want"})["kind"] == "variable"


def test_local_category_to_custom_payload_uses_given_parent():
    category = {"name": "Subscriptions", "kind": "variable"}
    payload = mapping.local_category_to_custom_payload(category, parent_id="parent-uuid")
    assert payload["parentId"] == "parent-uuid"
    assert payload["cardinality"] == "want"


# ================================================================
# standing orders -> bills
# ================================================================
def test_standing_order_to_bill_fields_extracts_due_day():
    order = {"name": "Netflix", "amount": 120000, "dueDate": "2026-08-15", "recurrenceRule": "FREQ=MONTHLY;INTERVAL=1"}
    fields = mapping.standing_order_to_bill_fields(order)
    assert fields["due_day"] == 15
    assert fields["cadence"] == "monthly"
    assert fields["amount"] == 120000


def test_standing_order_to_bill_fields_weekly_cadence():
    order = {"name": "Gym", "amount": 50000, "recurrenceRule": "FREQ=WEEKLY"}
    assert mapping.standing_order_to_bill_fields(order)["cadence"] == "weekly"


# ================================================================
# goals — targetAmount is a MonetaryAmount object on the live API, not a
# bare number (confirmed 2026-08-12: {"value": 4000000, "currencyCode":
# "IDR"}), which round_idr() must unwrap rather than crash on.
# ================================================================
def test_goal_to_local_fields_unwraps_monetary_amount_object():
    goal = {"id": "g1", "name": "Emergency fund", "targetAmount": {"value": 16000000, "currencyCode": "IDR"}, "state": "active"}
    fields = mapping.goal_to_local_fields(goal)
    assert fields["target_amount"] == 16000000
    assert fields["archived"] is False


def test_goal_to_local_fields_reached_state_is_archived():
    goal = {"id": "g1", "name": "Timberland", "targetAmount": {"value": 4000000}, "state": "reached"}
    assert mapping.goal_to_local_fields(goal)["archived"] is True


def test_round_idr_accepts_bare_number_or_monetary_object():
    assert mapping.round_idr(120000) == 120000
    assert mapping.round_idr({"value": 120000, "currencyCode": "IDR"}) == 120000
    assert mapping.round_idr({"currencyCode": "IDR"}) == 0
    assert mapping.round_idr(None) == 0


# ================================================================
# push payloads
# ================================================================
def test_transaction_to_record_payload_negates_expense_amount():
    txn = {"amount": 30000, "direction": "expense", "occurred_at": "2026-08-01 09:00", "note": "Lunch"}
    payload = mapping.transaction_to_record_payload(txn, account_id="acc-1", category_id="cat-1")
    assert payload["amount"] == -30000
    assert payload["accountId"] == "acc-1"
    assert payload["categoryId"] == "cat-1"
    assert payload["note"] == "Lunch"
    assert payload["recordDate"] == "2026-08-01T09:00:00Z"


def test_transaction_to_record_payload_keeps_income_positive():
    txn = {"amount": 500000, "direction": "income", "occurred_at": "2026-08-01 09:00"}
    payload = mapping.transaction_to_record_payload(txn, account_id="acc-1")
    assert payload["amount"] == 500000
    assert "categoryId" not in payload


def test_transaction_to_record_patch_only_includes_changed_metadata():
    txn = {"note": "Updated note"}
    patch = mapping.transaction_to_record_patch(txn, category_id="cat-2", label_ids=["l1"])
    assert patch == {"categoryId": "cat-2", "note": "Updated note", "labelIds": ["l1"]}


def test_transaction_to_record_patch_empty_when_nothing_to_change():
    assert mapping.transaction_to_record_patch({}) == {}
