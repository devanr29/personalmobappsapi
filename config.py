from dotenv import load_dotenv
load_dotenv("environtment.env")

import os, datetime, pytz
from google import genai
from groq import Groq

# ================================================================
# TIMEZONE HELPERS
# ================================================================
TZ_JKT = pytz.timezone("Asia/Jakarta")

def now_jkt() -> datetime.datetime:
    """Current datetime in Asia/Jakarta (naive, for DB storage)."""
    return datetime.datetime.now(TZ_JKT).replace(tzinfo=None)

def localize_jkt(dt: datetime.datetime) -> datetime.datetime:
    """Attach Asia/Jakarta tzinfo to a naive datetime (for Google Calendar)."""
    return TZ_JKT.localize(dt)

# ================================================================
# AI MODEL NAMES
# ================================================================
MODEL_EMBED      = "gemini-embedding-2-preview"    # Gemini Embedding 2  — semantic memory
MODEL_BRAINSTORM = "gemini-3-flash-preview"         # Gemini 3 Flash      — brainstorming
MODEL_GROQ       = "llama-3.1-8b-instant"           # Groq                — primary (classifier, chat, parsers)
MODEL_FALLBACK   = "gemini-3.1-flash-lite-preview"  # Gemini Flash Lite   — fallback if Groq errors

# ================================================================
# AI CLIENTS
# ================================================================
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
groq_client   = Groq(api_key=os.environ["GROQ_API_KEY"])

# ================================================================
# EXTERNAL APIS
# ================================================================
NEWS_API_KEY   = os.environ["NEWS_API_KEY"]
API_NINJAS_KEY = os.environ["API_NINJAS_KEY"]

# ================================================================
# GOOGLE
# ================================================================
SPREADSHEET_ID     = os.environ["GOOGLE_SHEET_ID"]
LOG_SPREADSHEET_ID = os.environ["LOG_SHEET_ID"]

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/tasks",
]

# ================================================================
# PAGINATION
# ================================================================
MAX_LIST_ITEMS = 60   # cap on items returned/displayed for a "show all" list

# ================================================================
# MOBILE API
# ================================================================
MOBILE_API_TOKEN = os.environ.get("MOBILE_API_TOKEN", "")

# ================================================================
# CONVERSATION
# ================================================================
CONV_WINDOW = 10   # keep last N user+assistant pairs in context

# ================================================================
# BUDGET
# ================================================================
# Fallback pay-cycle day when bot_state["payroll_day"] hasn't been set —
# see features/budget/service.get_payroll_day(). The setup wizard
# (POST /api/budget/setup) is the actual source of wallets/categories/
# bills; there are no fallback defaults for those anymore.
PAYROLL_DAY = 25

# Wallet by BudgetBakers REST API token (JWT, 90-day expiry, minted in the
# Wallet web app). Optional — sync features degrade to "unavailable"
# rather than crashing boot when unset, since this is a personal
# integration and not core to the app.
WALLET_API_TOKEN = os.environ.get("WALLET_API_TOKEN", "")
WALLET_API_BASE_URL = "https://rest.budgetbakers.com/wallet"
