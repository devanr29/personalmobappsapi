# Must run before anything builds an SSL context (Groq/Gemini/Google clients) —
# makes Python trust the OS cert store instead of only the certifi bundle, so
# corporate networks that intercept TLS with their own root CA still verify.
import truststore
truststore.inject_into_ssl()

# At the top with your other imports
import logging
from tracer import get_trace_id

import os
from flask import Flask, request

# ── Startup sequence (order matters) ────────────────────────────
from logging_setup import setup_logging
setup_logging()

from database import init_db

from scheduler import scheduler, register_jobs
from logging_setup import get_all_logs

# ── Flask app ────────────────────────────────────────────────────
app = Flask(__name__)
@app.after_request
def log_response(response):
    logger.info(f"[{get_trace_id()}] ◀ RESPONSE: HTTP {response.status_code}")
    return response

# ── Mobile REST API ──────────────────────────────────────────────
from api import api_bp
app.register_blueprint(api_bp, url_prefix="/api")

from features.budget import budget_bp
app.register_blueprint(budget_bp, url_prefix="/api/budget")

# ── DB + Scheduler ───────────────────────────────────────────────
init_db()

# scheduler.py's jobs (reminder polling, budget alerts, daily quotes) are
# not needed on a deploy you only hit on demand — and on a scale-to-zero
# host, every cold start would otherwise spin up its own copy, which would
# double-fire notifications against the same DB as your laptop. Defaults
# ON so local behavior is unchanged; set ENABLE_SCHEDULER=0 on hosts where
# you don't want it (e.g. Render).
if os.environ.get("ENABLE_SCHEDULER", "1") != "0":
    register_jobs()
    scheduler.start()

# ── tracer log ───────────────────────────────────────────────
from tracer import trace, logger, get_trace_id


def _safe_int(value):
    """Best-effort int parse; returns None for missing/non-numeric input instead of crashing."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ================================================================
# /logs — browser log viewer (auto-refreshes every 10s)
# ================================================================
@app.route("/logs")
def logs_endpoint():
    secret = os.environ.get("LOG_SECRET", "")
    if secret and request.args.get("secret") != secret:
        return "Unauthorized — add ?secret=YOUR_LOG_SECRET to the URL", 401
    n    = min(_safe_int(request.args.get("n")) or 100, 300)
    logs = get_all_logs(n).replace("<", "&lt;").replace(">", "&gt;")
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bot Logs</title>
  <meta http-equiv="refresh" content="10">
  <style>
    body {{ background:#0d1117; color:#c9d1d9; font-family:monospace; font-size:13px; padding:16px; margin:0 }}
    h2   {{ color:#58a6ff; margin-bottom:8px }}
    pre  {{ white-space:pre-wrap; word-break:break-all; line-height:1.6 }}
  </style>
</head>
<body>
  <h2>🖥️ Bot Logs <span style="font-size:11px;color:#8b949e">(auto-refresh 10s · last {n} lines)</span></h2>
  <pre>{logs}</pre>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html"}

# ================================================================
# ENTRY POINT
# ================================================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        debug=False,
        use_reloader=False,
        port=int(os.environ.get("PORT", 5000)),
    )
