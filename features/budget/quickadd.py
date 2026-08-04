"""Single-transaction natural-language quick-add: a deterministic parser
runs first and always (no network call), and an LLM parser fills in
whatever the deterministic pass left blank. The regex-found amount always
wins over the LLM's — deterministic beats stochastic on money."""
import json
import re

from ai.groq_client import groq_complete
from features.budget import repo

_AMOUNT_RE = re.compile(r"(?:rp\.?\s*)?(\d[\d.,]*)\s*(rb|ribu|k|jt|juta|m)?\b", re.IGNORECASE)
_THOUSAND_SUFFIXES = {"rb", "ribu", "k"}
_MILLION_SUFFIXES = {"jt", "juta", "m"}

_INCOME_KEYWORDS = {"gaji", "gajian", "masuk", "terima", "bonus", "refund", "income", "thr"}

_WALLET_KEYWORDS = {
    "ewallet": {"gopay", "ovo", "dana", "shopeepay", "linkaja"},
    "bank": {"bca", "mandiri", "bri", "bni", "transfer", "tf"},
    "cash": {"cash", "tunai"},
}


def _parse_decimal_last_sep_is_point(number_str: str) -> float:
    """With a magnitude suffix (rb/jt/...), the LAST '.'/',' is the decimal
    point and any earlier ones are thousand separators to strip — Indonesian
    numeral convention is the reverse of en-US."""
    last_sep = max(number_str.rfind("."), number_str.rfind(","))
    if last_sep == -1:
        return float(number_str)
    integer_part = number_str[:last_sep].replace(".", "").replace(",", "")
    decimal_part = number_str[last_sep + 1:]
    if not decimal_part.isdigit():
        return float(number_str.replace(",", "."))
    return float((integer_part or "0") + "." + decimal_part)


def parse_amount(text: str):
    """Returns (amount:int|None, span:(start,end)|None). Rejects bare
    values under 100 with no magnitude suffix as ambiguous (e.g. "beli 2
    nasi" must not become Rp 2)."""
    for match in _AMOUNT_RE.finditer(text):
        number_str, suffix = match.group(1), match.group(2)
        suffix = suffix.lower() if suffix else None
        if suffix in _THOUSAND_SUFFIXES or suffix in _MILLION_SUFFIXES:
            multiplier = 1_000 if suffix in _THOUSAND_SUFFIXES else 1_000_000
            amount = round(_parse_decimal_last_sep_is_point(number_str) * multiplier)
        else:
            cleaned = number_str.replace(".", "").replace(",", "")
            try:
                amount = int(cleaned)
            except ValueError:
                continue
            if amount < 100:
                continue
        return amount, match.span()
    return None, None


def parse_direction(text: str) -> str:
    lowered = text.lower()
    if any(re.search(r"\b" + re.escape(kw) + r"\b", lowered) for kw in _INCOME_KEYWORDS):
        return "income"
    return "expense"


def _category_keywords(category: dict) -> list[str]:
    if not category.get("keywords"):
        return []
    try:
        return [k.lower() for k in json.loads(category["keywords"])]
    except (ValueError, TypeError):
        return []


def score_category(text: str, category: dict) -> int:
    lowered = text.lower()
    score = 0
    for kw in _category_keywords(category):
        if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
            score += 3
    for token in re.findall(r"\w+", category["name"].lower()):
        if len(token) >= 3 and re.search(r"\b" + re.escape(token) + r"\b", lowered):
            score += 2
    return score


def match_category(text: str, categories: list[dict]):
    scored = [(score_category(text, c), c) for c in categories]
    scored = [(s, c) for s, c in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("sort_order", 0)))
    return scored[0][1]


def match_wallet(text: str, wallets: list[dict]):
    lowered = text.lower()
    for kind, keywords in _WALLET_KEYWORDS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
                match = next((w for w in wallets if w["kind"] == kind), None)
                if match:
                    return match
    return next((w for w in wallets if w["is_default"]), None)


def _strip_span(text: str, span) -> str:
    if span is None:
        return text
    start, end = span
    return (text[:start] + " " + text[end:]).strip()


def parse_local(message: str, categories: list[dict] | None = None, wallets: list[dict] | None = None) -> dict:
    categories = categories if categories is not None else repo.get_categories()
    wallets = wallets if wallets is not None else repo.get_wallets()

    amount, span = parse_amount(message)
    direction = parse_direction(message)
    category = match_category(message, categories)
    wallet = match_wallet(message, wallets)
    note = _strip_span(message, span) or message.strip()

    if amount is None:
        confidence = 0.0
    elif category and wallet:
        confidence = 1.0
    elif category:
        confidence = 0.8
    else:
        confidence = 0.5

    return {
        "amount": amount,
        "direction": direction,
        "category_id": category["id"] if category else None,
        "wallet_id": wallet["id"] if wallet else None,
        "note": note,
        "confidence": confidence,
        "source": "quick_regex",
    }


_LLM_SYSTEM_PROMPT = (
    "You extract exactly ONE money entry from a short Indonesian or English "
    "message. Reply with a single JSON object and nothing else."
)


def _build_llm_prompt(message: str, categories: list[dict], wallets: list[dict], now_str: str) -> str:
    category_lines = "\n".join(
        f"{c['id']}: {c['name']}" + (f" ({', '.join(_category_keywords(c))})" if _category_keywords(c) else "")
        for c in categories
    )
    wallet_lines = "\n".join(f"{w['id']}: {w['name']} ({w['kind']})" for w in wallets)
    return f"""Today is {now_str} (Asia/Jakarta).

Categories (use the id, never invent one):
{category_lines}

Wallets:
{wallet_lines}

Rules:
- Currency is IDR. "rb"/"ribu"/"k" = thousands, "jt"/"juta" = millions.
  "50rb" = 50000, "1,5jt" = 1500000.
- amount is a positive integer, never a string, never negative.
- direction: "expense" unless the message is about receiving money.
- categoryId/walletId must come from the lists above, or be null.
- note: 1-4 words describing what was bought, in the user's language.
- occurredAt: "YYYY-MM-DD HH:MM", or null for now.

Reply ONLY with:
{{"amount": <int|null>, "categoryId": <int|null>, "walletId": <int|null>,
 "direction": "expense"|"income", "note": "<string>", "occurredAt": <string|null>}}

User message: {message}"""


def parse_llm(message: str, categories: list[dict], wallets: list[dict], now_str: str) -> dict | None:
    valid_category_ids = {c["id"] for c in categories}
    valid_wallet_ids = {w["id"] for w in wallets}
    try:
        raw = groq_complete(
            system_prompt=_LLM_SYSTEM_PROMPT,
            user_prompt=_build_llm_prompt(message, categories, wallets, now_str),
            max_tokens=200,
            temperature=0.0,
        )
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
    except Exception:
        return None

    category_id = parsed.get("categoryId")
    if category_id not in valid_category_ids:
        category_id = None
    wallet_id = parsed.get("walletId")
    if wallet_id not in valid_wallet_ids:
        wallet_id = None

    return {
        "amount": parsed.get("amount"),
        "direction": parsed.get("direction") if parsed.get("direction") in ("expense", "income") else "expense",
        "category_id": category_id,
        "wallet_id": wallet_id,
        "note": parsed.get("note"),
        "occurred_at": parsed.get("occurredAt"),
    }


def parse(message: str, now_str: str | None = None) -> dict:
    """The regex amount always wins; the LLM only fills fields the local
    parse left None, and only runs at all when local confidence < 0.8 —
    so a message the local parser already understood ("beli bensin 50rb")
    never makes a network call."""
    categories = repo.get_categories()
    wallets = repo.get_wallets()
    local = parse_local(message, categories, wallets)

    if local["confidence"] >= 0.8:
        return local

    if now_str is None:
        from config import now_jkt
        now_str = now_jkt().strftime("%Y-%m-%d %H:%M")

    llm = parse_llm(message, categories, wallets, now_str)
    if llm is None:
        return local

    merged = dict(local)
    if merged["amount"] is None and llm.get("amount"):
        merged["amount"] = llm["amount"]
    if merged["category_id"] is None and llm.get("category_id") is not None:
        merged["category_id"] = llm["category_id"]
    if merged["wallet_id"] is None and llm.get("wallet_id") is not None:
        merged["wallet_id"] = llm["wallet_id"]
    if llm.get("note"):
        merged["note"] = llm["note"]
    if llm.get("occurred_at"):
        merged["occurred_at"] = llm["occurred_at"]
    if llm.get("direction") == "income":
        merged["direction"] = "income"

    merged["source"] = "quick_regex" if local["amount"] is not None else "quick_llm"
    return merged
