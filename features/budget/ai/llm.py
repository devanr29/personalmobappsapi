"""The only place the budget AI layer talks to a model. narrate() hands
groq_complete a list of pre-computed facts (facts.py) and an instruction,
then refuses the reply unless every rupiah figure and percentage in it
traces back to one of those facts. A refused or failed call returns None
and every caller falls back to the facts' own text, so the model being
down, rate-limited, or making a number up never produces a wrong figure
on screen — at worst it produces a plainer one."""
import re

from ai.groq_client import groq_complete
from tracer import logger

_SHORTHAND = re.compile(r"(?i)(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(k|rb|ribu|jt|juta)\b")
_SHORTHAND_MULT = {"k": 1_000, "rb": 1_000, "ribu": 1_000, "jt": 1_000_000, "juta": 1_000_000}
_RUPIAH = re.compile(r"(?i)rp\.?\s*-?\s*(\d[\d.,]*)")
_GROUPED = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+(?![\d.,]*\d)")
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
# A shorthand figure ("1.2jt") is a rounding of an exact one — accept it
# within this relative distance of a fact's exact value.
_SHORTHAND_TOLERANCE = 0.05

_SYSTEM_PROMPT = (
    "You are a careful personal-finance assistant for one person in Indonesia. "
    "Money is Indonesian Rupiah, written like Rp 150.000. "
    "You are given FACTS that were computed exactly from the person's budget ledger. "
    "Rules: use only the FACTS; copy every amount and percentage exactly as written in the FACTS; "
    "never add, subtract, average, round or estimate numbers yourself; never invent categories, "
    "merchants or amounts; if the FACTS do not answer something, say so plainly. "
    "Be warm, direct and brief. No preamble, no sign-off, no markdown headings."
)


def _to_int(digits: str) -> int:
    return int(re.sub(r"[.,]", "", digits))


def extract_figures(text: str) -> tuple:
    """(exact rupiah amounts, shorthand rupiah amounts, percentages) quoted
    in `text`, all as absolute values. Shorthand is pulled out first so
    '1,5 juta' isn't also read as the exact amount 15."""
    shorthand = []
    for m in _SHORTHAND.finditer(text):
        value = float(m.group(1).replace(",", "."))
        shorthand.append(round(value * _SHORTHAND_MULT[m.group(2).lower()]))
    rest = _SHORTHAND.sub(" ", text)
    percents = [float(m.group(1).replace(",", ".")) for m in _PERCENT.finditer(rest)]
    rest = _PERCENT.sub(" ", rest)
    exact = [_to_int(m.group(1)) for m in _RUPIAH.finditer(rest)]
    rest = _RUPIAH.sub(" ", rest)
    exact += [_to_int(m.group(0)) for m in _GROUPED.finditer(rest)]
    return exact, shorthand, percents


def numbers_grounded(reply: str, facts: list) -> bool:
    """Whether every figure in `reply` appears in `facts`. A reply with no
    figures at all is grounded (and fine — the facts are shown beside it)."""
    allowed_exact, allowed_short, allowed_pct = set(), set(), set()
    for f in facts:
        exact, short, pct = extract_figures(f["text"])
        allowed_exact.update(exact)
        allowed_short.update(short)
        allowed_pct.update(pct)
    allowed_money = allowed_exact | allowed_short

    exact, short, pct = extract_figures(reply)
    for value in exact:
        if value not in allowed_money:
            return False
    for value in short:
        if not any(abs(value - a) <= max(a, 1) * _SHORTHAND_TOLERANCE for a in allowed_money):
            return False
    for value in pct:
        if not any(abs(value - a) <= 1 for a in allowed_pct):
            return False
    return True


def narrate(facts: list, instruction: str, max_tokens: int = 400):
    """The model's phrasing of `facts` per `instruction`, or None when
    there are no facts, the call fails, or the reply isn't grounded."""
    if not facts:
        return None
    facts_block = "\n".join(f"- {f['text']}" for f in facts)
    try:
        reply = groq_complete(
            _SYSTEM_PROMPT,
            f"FACTS:\n{facts_block}\n\nTASK: {instruction}",
            max_tokens=max_tokens,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"budget ai narrate failed: {e}")
        return None
    reply = (reply or "").strip()
    if not reply:
        return None
    if not numbers_grounded(reply, facts):
        logger.warning(f"budget ai reply rejected, ungrounded figure: {reply!r}")
        return None
    return reply


_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def split_bullets(text: str, limit: int = 5) -> list:
    """Model output -> clean bullet strings (markers and bold stripped)."""
    bullets = []
    for line in text.splitlines():
        line = _BULLET_PREFIX.sub("", line).replace("**", "").strip()
        if line:
            bullets.append(line)
    return bullets[:limit]
