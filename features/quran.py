import json, random, re, requests
from google.genai import types

from config import gemini_client, MODEL_BRAINSTORM, MODEL_FALLBACK, now_jkt
from database import state_get, state_set
from tracer import trace

# Verse text and translation always come from alquran.cloud, never from an
# LLM. The "story/context" is grounded in Tafsir Ibn Kathir (spa5k/tafsir_api
# on jsDelivr); Gemini only summarizes that tafsir and writes the reflection.
_QURAN_API   = "https://api.alquran.cloud/v1"
_TAFSIR_API  = "https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/en-tafisr-ibn-kathir"
_TOTAL_AYAHS = 6236
_WINDOW      = 4       # neighbouring verses shown on each side of the target
_TAFSIR_MAX  = 8000    # chars of tafsir sent to the model
_SOURCES     = {"translation": "Sahih International", "tafsir": "Ibn Kathir"}

_REF_RE = re.compile(r"\b(\d{1,3})\s*:\s*(\d{1,3})\b")


def parse_ref(text: str) -> str | None:
    """'2:255' out of free text, or None."""
    m = _REF_RE.search(text or "")
    if not m:
        return None
    surah, ayah = int(m.group(1)), int(m.group(2))
    if 1 <= surah <= 114 and ayah >= 1:
        return f"{surah}:{ayah}"
    return None


def _get(url: str) -> dict | None:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Quran fetch error] {url}: {e}")
        return None


@trace
def _fetch_ayah(ref) -> dict | None:
    """Arabic + Sahih International for one ayah. `ref` is '2:255' or a
    global ayah number (1–6236)."""
    data = _get(f"{_QURAN_API}/ayah/{ref}/editions/quran-uthmani,en.sahih")
    if not data or data.get("code") != 200:
        return None
    arabic, english = data["data"][0], data["data"][1]
    return {
        "ref":         f"{english['surah']['number']}:{english['numberInSurah']}",
        "surah":       english["surah"]["englishName"],
        "surahNumber": english["surah"]["number"],
        "ayah":        english["numberInSurah"],
        "arabic":      arabic["text"],
        "translation": english["text"],
        "ruku":        english["ruku"],
    }


@trace
def _fetch_passage(ruku: int) -> list[dict] | None:
    """The ruku (section) as [{surah, ayah, ref, translation}]."""
    data = _get(f"{_QURAN_API}/ruku/{ruku}/en.sahih")
    if not data or data.get("code") != 200:
        return None
    return [
        {
            "surah": a["surah"]["number"],
            "ayah": a["numberInSurah"],
            "ref": f"{a['surah']['number']}:{a['numberInSurah']}",
            "translation": a["text"],
        }
        for a in data["data"]["ayahs"]
    ]


@trace
def _fetch_tafsir(surah: int, ayah: int) -> str | None:
    data = _get(f"{_TAFSIR_API}/{surah}/{ayah}.json")
    text = (data or {}).get("text", "").strip()
    return text or None


def _tafsir_for(verse: dict, section: list[dict]) -> tuple[str | None, str | None]:
    """Ibn Kathir often comments on a group of verses at the group's first
    verse, so an empty entry walks back to the nearest non-empty one within
    the same section. Returns (tafsir text, ref it belongs to)."""
    earlier = [v for v in section if v["surah"] == verse["surahNumber"] and v["ayah"] <= verse["ayah"]]
    candidates = sorted({v["ayah"] for v in earlier} | {verse["ayah"]}, reverse=True)
    for ayah in candidates:
        text = _fetch_tafsir(verse["surahNumber"], ayah)
        if text:
            return text[:_TAFSIR_MAX], f"{verse['surahNumber']}:{ayah}"
    return None, None


def _passage_window(verse: dict, section: list[dict] | None) -> dict:
    section = section or []
    idx = next((i for i, v in enumerate(section) if v["ref"] == verse["ref"]), None)
    if idx is None:
        return {"range": verse["ref"], "verses": [], "isMidPassage": False}
    window = section[max(0, idx - _WINDOW): idx + _WINDOW + 1]
    first, last = window[0], window[-1]
    rng = first["ref"] if first is last else f"{first['ref']}–{last['ayah']}"
    return {
        "range": rng,
        "verses": [{"ref": v["ref"], "translation": v["translation"]} for v in window],
        "isMidPassage": len(section) > 1,
    }


_REFLECT_PROMPT = """You help a Muslim reflect on one verse of the Quran. Write in English.

VERSE {ref} (Surah {surah}), Sahih International:
"{translation}"

SURROUNDING PASSAGE (same section, Sahih International):
{passage}

TAFSIR IBN KATHIR{tafsir_note}:
{tafsir}

Return JSON with exactly these keys:
- "context": 2-4 sentences on the story / occasion of revelation (asbab al-nuzul) of this verse, taken ONLY from the tafsir above. If the tafsir mentions no specific occasion, say plainly that no specific occasion of revelation is recorded for it, then describe what the passage is about.
- "passageNote": {passage_instruction}
- "reflection": a list of 2-3 short, practical points on how to reflect on and live by this verse today.

Rules: only use Quran text given above; never quote or paraphrase other verses from memory. Never invent hadith, narrators or scholars - if the tafsir names one you may mention it. Be respectful and humble; no fatwas."""


def _reflect(verse: dict, passage: dict, tafsir: str | None, tafsir_ref: str | None) -> dict | None:
    if passage["isMidPassage"]:
        passage_instruction = ("1-2 sentences on how this verse connects to the verses before and "
                               "after it in the passage, citing their refs (e.g. 2:254).")
    else:
        passage_instruction = "null (the verse stands alone)."
    note = "" if not tafsir_ref or tafsir_ref == verse["ref"] else f" (commentary given at {tafsir_ref}, covering this verse)"
    prompt = _REFLECT_PROMPT.format(
        ref=verse["ref"], surah=verse["surah"], translation=verse["translation"],
        passage="\n".join(f"{v['ref']}: {v['translation']}" for v in passage["verses"]) or "(not available)",
        tafsir=tafsir or "(not available - say the context could not be loaded, and describe only the passage's theme)",
        tafsir_note=note, passage_instruction=passage_instruction,
    )
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3)
    for model in (MODEL_BRAINSTORM, MODEL_FALLBACK):
        try:
            resp = gemini_client.models.generate_content(model=model, contents=prompt, config=config)
            out = json.loads(resp.text)
            reflection = out.get("reflection") or []
            if isinstance(reflection, str):
                reflection = [reflection]
            return {
                "context":     out.get("context") or None,
                "passageNote": out.get("passageNote") or None,
                "reflection":  [str(r) for r in reflection] or None,
            }
        except Exception as e:
            print(f"[Quran reflect error] {model}: {e}")
    return None


@trace
def get_verse(ref) -> dict | None:
    """Full chat payload for one verse. Cached per ref once the reflection
    succeeded, so opening the same verse again doesn't regenerate it."""
    cache_key = f"quran_verse:{ref}" if isinstance(ref, str) else None
    if cache_key:
        cached = state_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    verse = _fetch_ayah(ref)
    if not verse:
        return None
    section = _fetch_passage(verse["ruku"])
    passage = _passage_window(verse, section)
    tafsir, tafsir_ref = _tafsir_for(verse, section or [])
    reflected = _reflect(verse, passage, tafsir, tafsir_ref) or {}

    payload = {
        "ref":         verse["ref"],
        "surah":       verse["surah"],
        "surahNumber": verse["surahNumber"],
        "ayah":        verse["ayah"],
        "arabic":      verse["arabic"],
        "translation": verse["translation"],
        "passage":     {**passage, "note": reflected.get("passageNote")},
        "context":     reflected.get("context"),
        "reflection":  reflected.get("reflection"),
        "sources":     dict(_SOURCES, tafsir=_SOURCES["tafsir"] if tafsir else None),
    }
    if payload["context"]:
        state_set(f"quran_verse:{verse['ref']}", json.dumps(payload, ensure_ascii=False))
    return payload


def pick_random_ref() -> int:
    return random.randint(1, _TOTAL_AYAHS)


@trace
def find_by_topic(keyword: str) -> str | None:
    """A random verse whose Sahih International text mentions `keyword`."""
    keyword = (keyword or "").strip()
    if not keyword:
        return None
    data = _get(f"{_QURAN_API}/search/{requests.utils.quote(keyword)}/all/en.sahih")
    if not data or data.get("code") != 200:
        return None
    matches = data["data"].get("matches") or []
    if not matches:
        return None
    m = random.choice(matches)
    return f"{m['surah']['number']}:{m['numberInSurah']}"


def _card(verse: dict) -> dict:
    return {"ref": verse["ref"], "surah": verse["surah"], "translation": verse["translation"]}


def _save_verse_of_day(verse: dict):
    state_set("quran_of_day", json.dumps({**_card(verse), "at": now_jkt().isoformat()}, ensure_ascii=False))


@trace
def get_verse_of_day() -> dict | None:
    """Verse for Home's card: the latest one the scheduler pushed, so the
    card matches the notification. No LLM call on this path."""
    cached = state_get("quran_of_day")
    if cached:
        try:
            return _card(json.loads(cached))
        except Exception:
            pass
    verse = _fetch_ayah(pick_random_ref())
    if not verse:
        return None
    _save_verse_of_day(verse)
    return _card(verse)


def _truncate(text: str, limit: int = 180) -> str:
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


@trace
def send_scheduled_verse():
    """05:00 and 20:00 WIB push (called by scheduler); the pushed verse
    becomes the Home card's verse. The reflection is built lazily on the
    first chat open, then cached."""
    try:
        verse = _fetch_ayah(pick_random_ref())
        if not verse:
            print("[Quran scheduler] Could not fetch a verse; keeping the current card.")
            return
        _save_verse_of_day(verse)
        from push import send_push_notification
        title = f"QS {verse['surah']} {verse['ref']}"
        if send_push_notification(title, _truncate(verse["translation"]), {"verse": verse["ref"]}):
            print(f"[Quran scheduler] {verse['ref']} sent successfully.")
        else:
            print(f"[Quran scheduler] {verse['ref']} not delivered.")
    except Exception as e:
        print(f"[Quran scheduler] Failed to send verse: {e}")
