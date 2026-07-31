import json
import requests

from database import state_get, state_set
from tracer import trace, logger

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _get_tokens() -> list[str]:
    raw = state_get("push_tokens")
    return json.loads(raw) if raw else []


@trace
def register_push_token(token: str):
    tokens = _get_tokens()
    if token not in tokens:
        tokens.append(token)
        state_set("push_tokens", json.dumps(tokens))


@trace
def send_push_notification(title: str, body: str, data: dict = None):
    """POSTs one Expo push message per registered device. Requires a dev
    build or EAS development build on the client — Expo Go doesn't support
    remote push on current SDKs."""
    tokens = _get_tokens()
    if not tokens:
        return
    messages = [
        {"to": t, "title": title, "body": body, "data": data or {}}
        for t in tokens
    ]
    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"send_push_notification failed: {e}")
