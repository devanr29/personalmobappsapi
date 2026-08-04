"""Shared REST plumbing for every blueprint: response envelope, CORS,
bearer-token auth, and the catch-all error mapper.

Named api_common.py rather than http.py deliberately — a root-level http.py
would shadow the stdlib http package for every module in this process
(requests, urllib3, werkzeug and Flask itself all import it), which would
break in confusing, hard-to-trace ways.

Blueprint hooks (before_request/after_request/errorhandler) do not inherit
across blueprints, so each blueprint wires these functions into its own
decorators rather than importing a decorated route.
"""
import hmac
import time

from flask import g, jsonify, request

from config import MOBILE_API_TOKEN
from tracer import get_trace_id, logger


def ok(data, status=200, meta=None):
    return jsonify({"data": data, "meta": meta or {}}), status


def err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}, "meta": {}}), status


# ================================================================
# CORS — needed for the Expo *web* build, which runs in the browser
# at a different origin (localhost:8081) than the API. Native (Expo
# Go / device) fetches have no origin and are unaffected. Token auth
# rides in the Authorization header (not cookies), so a wildcard
# origin is safe — we're not using credentialed requests.
# ================================================================
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return resp


# ================================================================
# AUTH — bearer token, constant-time compare (avoids a timing
# side-channel on a URL that's publicly reachable on Railway)
# ================================================================
def check_auth(exempt_paths=()):
    """Call from a blueprint's before_request. Returns an error response
    to short-circuit the request, or None to let it proceed."""
    # CORS preflight carries no Authorization header — let Flask's
    # automatic OPTIONS handler answer it; after_request adds headers.
    if request.method == "OPTIONS":
        return None
    if request.path in exempt_paths:
        return None
    auth  = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not MOBILE_API_TOKEN or not hmac.compare_digest(token, MOBILE_API_TOKEN):
        return err("UNAUTHORIZED", "Missing or invalid bearer token.", 401)
    return None


def handle_unexpected_error(e, tag="api"):
    logger.warning(f"[{tag}] unhandled error: {e}")
    return err("INTERNAL_ERROR", "Something went wrong.", 500)


# ================================================================
# TIMING — every mobile-facing route logs its own wall-clock time.
# Added after GET /api/home and GET /api/budget were observed hanging on
# the mobile app with nothing in the logs to say why; each aggregate
# fanned out into 8-10 db_conn() calls, and against the remote Postgres
# host each one cost seconds. Call start_timer() as the FIRST
# before_request (registered ahead of check_auth, so even a rejected
# request gets timed) and log_timing() as an after_request — logs
# "METHOD path — Nms" to bot_all.log / the /logs page so a slow endpoint
# shows up immediately instead of requiring a one-off script to find.
# ================================================================
def start_timer():
    g._req_start = time.monotonic()


def log_timing(resp):
    start = getattr(g, "_req_start", None)
    if start is not None:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"[{get_trace_id()}] {request.method} {request.path} — {elapsed_ms}ms")
    return resp
