import json, requests
from config import now_jkt, API_NINJAS_KEY
from database import state_get, state_set
from tracer import trace

_QUOTE_CATEGORY_MAP = {
    "motivat": "inspirational",
    "inspir":  "inspirational",
    "success": "success",
    "sukses":  "success",
    "life":    "life",
    "hidup":   "life",
    "happi":   "happiness",
    "bahagia": "happiness",
    "love":    "love",
    "cinta":   "love",
    "wisdom":  "wisdom",
    "bijak":   "wisdom",
    "work":    "work",
    "kerja":   "work",
    "friend":  "friendship",
    "teman":   "friendship",
    "morning": "morning",
    "pagi":    "morning",
    "humour":  "humor",
    "humor":   "humor",
    "funny":   "humor",
    "fear":    "courage",
    "brave":   "courage",
    "berani":  "courage",
}
@trace
def _fetch_ninja_quote(categories: str = "") -> dict | None:
    try:
        url    = "https://api.api-ninjas.com/v2/randomquotes"
        params = {"category": categories} if categories else {}
        resp   = requests.get(url, headers={"X-Api-Key": API_NINJAS_KEY}, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0]
    except Exception as e:
        print(f"[API Ninjas quote error] {e}")
    return None

def _italic(text: str) -> str:
    """Push bodies are plain text, so markdown italics show up as literal
    underscores. Map ASCII letters to Unicode sans-serif italic instead."""
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(0x1D608 + ord(ch) - ord("A")))
        elif "a" <= ch <= "z":
            out.append(chr(0x1D622 + ord(ch) - ord("a")))
        else:
            out.append(ch)
    return "".join(out)

@trace
def _pick_category(context: str) -> str:
    lower = context.lower()
    for keyword, category in _QUOTE_CATEGORY_MAP.items():
        if keyword in lower:
            return category
    return "inspirational"

@trace
def generate_daily_quote(context: str = "") -> str:
    category = _pick_category(context) if context else "inspirational"
    raw = _fetch_ninja_quote(category) or _fetch_ninja_quote()

    if not raw:
        return "*Keep going — every step forward counts, no matter how small.*"

    quote  = raw.get("quote", "")
    author = raw.get("author", "Unknown")
    return f"_{quote}_\n{author}"

def _save_quote_of_day(quote: str, author: str):
    today = now_jkt().strftime("%Y-%m-%d")
    state_set("quote_of_day", json.dumps({"date": today, "quote": quote, "author": author}))

@trace
def get_quote_of_day() -> dict:
    """Quote for Home's Quote card: the latest quote the scheduler pushed,
    so the card matches the notification. Falls back to fetching one when
    nothing was pushed today. Chat's on-demand 'give me a quote' intent
    keeps using fresh generate_daily_quote()."""
    today = now_jkt().strftime("%Y-%m-%d")
    cached = state_get("quote_of_day")
    if cached:
        try:
            data = json.loads(cached)
            if data.get("date") == today:
                return {"quote": data["quote"], "author": data["author"]}
        except Exception:
            pass

    raw = _fetch_ninja_quote("inspirational") or _fetch_ninja_quote()
    if raw:
        quote, author = raw.get("quote", ""), raw.get("author", "Unknown")
    else:
        quote, author = "Keep going — every step forward counts, no matter how small.", ""

    _save_quote_of_day(quote, author)
    return {"quote": quote, "author": author}

@trace
def send_scheduled_quote(label: str | None = None):
    """Send an auto-scheduled quote via Expo push (called by scheduler) and
    make it the Home Quote card's quote. The title is the quote's author;
    the label (chosen from the current WIB hour when omitted) is the title
    only when there is no author, and is used in logs."""
    if label is None:
        hour = now_jkt().hour
        if hour == 6:
            label = "Good Morning 🌅"
        elif hour == 21:
            label = "Good Night 🌙"
        else:
            label = "Quote of the Moment ✨"
    try:
        raw = _fetch_ninja_quote("inspirational") or _fetch_ninja_quote()
        if raw:
            quote, author = raw.get("quote", ""), raw.get("author", "Unknown")
            _save_quote_of_day(quote, author)
            title = author if author and author != "Unknown" else label
            body = _italic(quote)
        else:
            title = label
            body = _italic("Keep going — every step forward counts, no matter how small.")
        from push import send_push_notification
        if send_push_notification(title, body):
            print(f"[Quote scheduler] {label} quote sent successfully.")
        else:
            print(f"[Quote scheduler] {label} quote not delivered.")
    except Exception as e:
        print(f"[Quote scheduler] Failed to send {label} quote: {e}")
