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


# ================================================================
# round_idr — the live API returns MonetaryAmount objects, not bare
# numbers (confirmed 2026-08-12: {"value": 4000000, "currencyCode":
# "IDR"}), which round_idr() must unwrap rather than crash on.
# ================================================================
def test_round_idr_accepts_bare_number_or_monetary_object():
    assert mapping.round_idr(120000) == 120000
    assert mapping.round_idr({"value": 120000, "currencyCode": "IDR"}) == 120000
    assert mapping.round_idr({"currencyCode": "IDR"}) == 0
    assert mapping.round_idr(None) == 0

