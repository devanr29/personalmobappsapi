from unittest.mock import patch

import pytest

from features.budget.quickadd import parse_amount, parse_direction, parse_local, parse

CATEGORIES = [
    {"id": 1, "name": "Fuel", "keywords": '["bensin", "pertalite", "pertamax", "bbm", "spbu"]', "sort_order": 0},
    {"id": 2, "name": "Food", "keywords": '["makan", "jajan", "warteg", "gofood"]', "sort_order": 1},
    {"id": 3, "name": "Laundry", "keywords": '["laundry", "cuci"]', "sort_order": 2},
]
WALLETS = [
    {"id": 1, "name": "Cash", "kind": "cash", "is_default": True},
    {"id": 2, "name": "GoPay", "kind": "ewallet", "is_default": False},
    {"id": 3, "name": "Bank", "kind": "bank", "is_default": False},
]


@pytest.mark.parametrize("text,expected", [
    ("50rb", 50_000),
    ("50k", 50_000),
    ("2jt", 2_000_000),
    ("1,5jt", 1_500_000),
    ("1.5jt", 1_500_000),
    ("50.000", 50_000),
    ("1.500.000", 1_500_000),
    ("50000", 50_000),
])
def test_amount_table(text, expected):
    amount, _ = parse_amount(text)
    assert amount == expected


def test_ambiguous_bare_small_number_is_rejected():
    amount, _ = parse_amount("beli 2 nasi")
    assert amount is None


def test_beli_bensin_50rb_matches_fuel_with_full_confidence():
    result = parse_local("beli bensin 50rb", CATEGORIES, WALLETS)
    assert result["amount"] == 50_000
    assert result["category_id"] == 1  # Fuel
    assert result["direction"] == "expense"
    assert result["confidence"] == 1.0
    assert result["source"] == "quick_regex"


def test_income_keyword_flips_direction():
    result = parse_local("gajian 5jt", CATEGORIES, WALLETS)
    assert result["direction"] == "income"
    assert result["amount"] == 5_000_000


def test_wallet_keyword_matches_gopay():
    result = parse_local("bayar laundry pakai gopay 60rb", CATEGORIES, WALLETS)
    assert result["wallet_id"] == 2
    assert result["category_id"] == 3


def test_no_category_keyword_match_falls_back_to_default_wallet():
    result = parse_local("50rb", CATEGORIES, WALLETS)
    assert result["category_id"] is None
    assert result["wallet_id"] == 1  # is_default


def test_full_confidence_parse_never_calls_the_llm():
    with patch("features.budget.quickadd.groq_complete") as mock_groq:
        with patch("features.budget.quickadd.repo") as mock_repo:
            mock_repo.get_categories.return_value = CATEGORIES
            mock_repo.get_wallets.return_value = WALLETS
            result = parse("beli bensin 50rb")
    mock_groq.assert_not_called()
    assert result["amount"] == 50_000
    assert result["source"] == "quick_regex"


def test_amount_found_survives_llm_failure():
    with patch("features.budget.quickadd.groq_complete", side_effect=RuntimeError("groq down")):
        with patch("features.budget.quickadd.repo") as mock_repo:
            mock_repo.get_categories.return_value = CATEGORIES
            mock_repo.get_wallets.return_value = WALLETS
            # "50rb" alone has no category match -> confidence 0.5, triggers
            # the LLM path, which we're forcing to fail here.
            result = parse("50rb")
    assert result["amount"] == 50_000


def test_no_amount_at_all_returns_none_amount():
    with patch("features.budget.quickadd.groq_complete", side_effect=RuntimeError("groq down")):
        with patch("features.budget.quickadd.repo") as mock_repo:
            mock_repo.get_categories.return_value = CATEGORIES
            mock_repo.get_wallets.return_value = WALLETS
            result = parse("beli sesuatu")
    assert result["amount"] is None
