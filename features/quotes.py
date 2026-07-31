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

@trace
def get_quote_of_day() -> dict:
    """Stable once-a-day quote for Home's Quote card. Chat's on-demand
    'give me a quote' intent keeps using fresh generate_daily_quote()."""
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

    state_set("quote_of_day", json.dumps({"date": today, "quote": quote, "author": author}))
    return {"quote": quote, "author": author}

@trace
def send_scheduled_quote(label: str):
    """Send an auto-scheduled quote via Expo push (called by scheduler)."""
    try:
        body = generate_daily_quote()
        from push import send_push_notification
        send_push_notification(label, body)
        print(f"[Quote scheduler] {label} quote sent successfully.")
    except Exception as e:
        print(f"[Quote scheduler] Failed to send {label} quote: {e}")
