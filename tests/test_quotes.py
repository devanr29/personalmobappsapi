from unittest.mock import patch

from features import quotes


def test_scheduled_quote_becomes_home_card_quote():
    store = {}
    with patch.object(quotes, "state_get", side_effect=store.get), \
         patch.object(quotes, "state_set", side_effect=store.__setitem__), \
         patch.object(quotes, "_fetch_ninja_quote", return_value={"quote": "Q1", "author": "A1"}), \
         patch("push.send_push_notification", return_value=True) as push:
        quotes.send_scheduled_quote("Title")

    push.assert_called_once_with("Title", "_Q1_\nA1")

    with patch.object(quotes, "state_get", side_effect=store.get), \
         patch.object(quotes, "_fetch_ninja_quote") as fetch:
        assert quotes.get_quote_of_day() == {"quote": "Q1", "author": "A1"}
    fetch.assert_not_called()


def test_failed_fetch_keeps_existing_card_quote():
    with patch.object(quotes, "state_set") as state_set, \
         patch.object(quotes, "_fetch_ninja_quote", return_value=None), \
         patch("push.send_push_notification", return_value=True):
        quotes.send_scheduled_quote("Title")
    state_set.assert_not_called()
