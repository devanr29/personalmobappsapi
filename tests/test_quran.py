import json
from unittest.mock import MagicMock, patch

from features import quran


VERSE = {
    "ref": "2:255", "surah": "Al-Baqara", "surahNumber": 2, "ayah": 255,
    "arabic": "ٱللَّهُ", "translation": "Allah - there is no deity except Him.", "ruku": 35,
}
SECTION = [
    {"surah": 2, "ayah": a, "ref": f"2:{a}", "translation": f"T{a}"} for a in range(254, 258)
]


def _gemini(text):
    resp = MagicMock()
    resp.text = text
    return resp


def _reflection_json():
    return json.dumps({"context": "C", "passageNote": "P", "reflection": ["R1", "R2"]})


def test_scheduled_verse_becomes_home_card_verse():
    store = {}
    with patch.object(quran, "state_get", side_effect=store.get), \
         patch.object(quran, "state_set", side_effect=store.__setitem__), \
         patch.object(quran, "_fetch_ayah", return_value=VERSE), \
         patch("push.send_push_notification", return_value=True) as push:
        quran.send_scheduled_verse()

    title, body, data = push.call_args.args
    assert title == "QS Al-Baqara 2:255"
    assert body == VERSE["translation"]
    assert data == {"verse": "2:255"}

    with patch.object(quran, "state_get", side_effect=store.get), \
         patch.object(quran, "_fetch_ayah") as fetch:
        assert quran.get_verse_of_day() == {
            "ref": "2:255", "surah": "Al-Baqara", "translation": VERSE["translation"],
        }
    fetch.assert_not_called()


def test_failed_fetch_keeps_existing_card_verse():
    with patch.object(quran, "state_set") as state_set, \
         patch.object(quran, "_fetch_ayah", return_value=None), \
         patch("push.send_push_notification") as push:
        quran.send_scheduled_verse()
    state_set.assert_not_called()
    push.assert_not_called()


def test_long_translation_is_truncated_for_push():
    long = dict(VERSE, translation="word " * 100)
    with patch.object(quran, "state_set"), \
         patch.object(quran, "_fetch_ayah", return_value=long), \
         patch("push.send_push_notification", return_value=True) as push:
        quran.send_scheduled_verse()
    body = push.call_args.args[1]
    assert len(body) <= 180 and body.endswith("…")


def test_empty_tafsir_walks_back_within_section():
    verse = dict(VERSE, ayah=256, ref="2:256")
    calls = []

    def tafsir(surah, ayah):
        calls.append(ayah)
        return "group commentary" if ayah == 254 else None

    with patch.object(quran, "_fetch_tafsir", side_effect=tafsir):
        text, ref = quran._tafsir_for(verse, SECTION)
    assert (text, ref) == ("group commentary", "2:254")
    assert calls == [256, 255, 254]


def test_mid_passage_verse_includes_neighbours():
    passage = quran._passage_window(VERSE, SECTION)
    assert passage["isMidPassage"] is True
    assert passage["range"] == "2:254–257"
    assert [v["ref"] for v in passage["verses"]] == ["2:254", "2:255", "2:256", "2:257"]


def test_standalone_verse_is_not_mid_passage():
    section = [{"surah": 2, "ayah": 255, "ref": "2:255", "translation": "T"}]
    assert quran._passage_window(VERSE, section)["isMidPassage"] is False


def _patched_sources(store):
    return (
        patch.object(quran, "state_get", side_effect=store.get),
        patch.object(quran, "state_set", side_effect=store.__setitem__),
        patch.object(quran, "_fetch_ayah", return_value=VERSE),
        patch.object(quran, "_fetch_passage", return_value=SECTION),
        patch.object(quran, "_fetch_tafsir", return_value="tafsir"),
    )


def test_verse_payload_and_cache():
    store = {}
    a, b, c, d, e = _patched_sources(store)
    with a, b, c, d, e, patch.object(quran.gemini_client.models, "generate_content",
                                     return_value=_gemini(_reflection_json())) as gen:
        first = quran.get_verse("2:255")
        second = quran.get_verse("2:255")

    assert gen.call_count == 1
    assert first == second
    assert first["translation"] == VERSE["translation"]
    assert first["context"] == "C"
    assert first["reflection"] == ["R1", "R2"]
    assert first["passage"]["note"] == "P"
    assert first["sources"] == {"translation": "Sahih International", "tafsir": "Ibn Kathir"}


def test_gemini_failure_still_returns_verse_and_is_not_cached():
    store = {}
    a, b, c, d, e = _patched_sources(store)
    with a, b, c, d, e, patch.object(quran.gemini_client.models, "generate_content",
                                     side_effect=RuntimeError("down")) as gen:
        verse = quran.get_verse("2:255")

    assert gen.call_count == 2  # primary + fallback model
    assert verse["translation"] == VERSE["translation"]
    assert verse["context"] is None and verse["reflection"] is None
    assert store == {}


def test_parse_ref():
    assert quran.parse_ref("quran 2:255") == "2:255"
    assert quran.parse_ref("explain 2 : 286 please") == "2:286"
    assert quran.parse_ref("115:1") is None
    assert quran.parse_ref("give me a verse") is None


def test_chat_fast_path_skips_classifier(client, auth_headers):
    payload = {"kind": "quran", "text": "t", "data": {"ref": "2:255"}}
    with patch("api.classify_intent") as classify, \
         patch("api.route_intent", return_value=payload) as route, \
         patch("api.save_conv_turn"):
        resp = client.post("/api/chat", json={"message": "quran 2:255"}, headers=auth_headers)

    assert resp.status_code == 200
    classify.assert_not_called()
    assert route.call_args.args[:2] == ("quran", {})


def test_quran_intent_resolution_order():
    import intents
    with patch.object(intents.quran, "get_verse", return_value=dict(VERSE)) as get, \
         patch.object(intents.quran, "find_by_topic", return_value="3:200") as topic:
        intents.route_intent("quran", {"keyword": "patience"}, "explain 2:255")
        assert get.call_args.args == ("2:255",)
        topic.assert_not_called()

        result = intents.route_intent("quran", {"keyword": "patience"}, "ayat about patience")
        assert get.call_args.args == ("3:200",)
        assert result["kind"] == "quran"
