import json
import threading
import requests

from database import state_get, state_set
from tracer import trace, logger

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"

# Expo only learns whether FCM/APNs accepted a message after the fact;
# errors like FCM's 403 PERMISSION_DENIED show up in the receipt, not the
# ticket. Receipts are usually ready within seconds.
RECEIPT_DELAY_SECONDS = 15


def _get_tokens() -> list[str]:
    raw = state_get("push_tokens")
    return json.loads(raw) if raw else []


def _remove_token(token: str):
    tokens = _get_tokens()
    if token in tokens:
        tokens.remove(token)
        state_set("push_tokens", json.dumps(tokens))
        logger.warning(f"push: removed unregistered device token {token[:30]}…")


def _describe_error(item: dict) -> str:
    details = item.get("details") or {}
    msg = f"{details.get('error', 'error')}: {item.get('message', '')}"
    fcm = details.get("fcm") or {}
    if fcm.get("response"):
        try:
            fcm_err = json.loads(fcm["response"]).get("error", {})
            msg += f" [FCM {fcm_err.get('code')} {fcm_err.get('status')}: {fcm_err.get('message', '')[:200]}]"
        except (ValueError, AttributeError):
            pass
    return msg


def _check_receipts(ticket_tokens: dict[str, str]):
    """Fetch delivery receipts for the given ticket ids and log failures.
    Runs off the caller's thread so senders aren't blocked waiting on it."""
    try:
        resp = requests.post(EXPO_RECEIPTS_URL, json={"ids": list(ticket_tokens)}, timeout=10)
        resp.raise_for_status()
        receipts = resp.json().get("data") or {}
    except Exception as e:
        logger.warning(f"push: could not fetch delivery receipts: {e}")
        return
    for ticket_id, receipt in receipts.items():
        if receipt.get("status") == "ok":
            continue
        logger.warning(f"push: delivery failed — {_describe_error(receipt)}")
        if (receipt.get("details") or {}).get("error") == "DeviceNotRegistered":
            _remove_token(ticket_tokens[ticket_id])


@trace
def register_push_token(token: str):
    tokens = _get_tokens()
    if token not in tokens:
        tokens.append(token)
        state_set("push_tokens", json.dumps(tokens))


@trace
def send_push_notification(title: str, body: str, data: dict = None) -> bool:
    """POSTs one Expo push message per registered device. Requires a dev
    build or EAS development build on the client — Expo Go doesn't support
    remote push on current SDKs. Returns whether Expo accepted at least one
    message — callers that need to know "did this actually reach anyone"
    (the budget alerts job, deciding whether to mark a log row delivered)
    should not treat a silent no-op as success. FCM/APNs failures only
    surface later in receipts, which are checked and logged in the
    background."""
    tokens = _get_tokens()
    if not tokens:
        logger.warning("send_push_notification: no registered push tokens — nothing to deliver.")
        return False
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
        tickets = resp.json().get("data") or []
    except Exception as e:
        logger.warning(f"send_push_notification failed: {e}")
        return False

    # Tickets come back in the same order as the messages.
    ticket_tokens = {}
    for token, ticket in zip(tokens, tickets):
        if ticket.get("status") == "ok":
            ticket_tokens[ticket["id"]] = token
            continue
        logger.warning(f"push: Expo rejected message — {_describe_error(ticket)}")
        if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
            _remove_token(token)

    if ticket_tokens:
        timer = threading.Timer(RECEIPT_DELAY_SECONDS, _check_receipts, args=(ticket_tokens,))
        timer.daemon = True
        timer.start()
    return bool(ticket_tokens)
