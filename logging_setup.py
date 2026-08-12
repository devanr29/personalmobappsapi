import logging, logging.handlers, threading, sys, time, datetime, collections
from config import LOG_SPREADSHEET_ID, TZ_JKT

_ALL_LOG_FILE   = "bot_all.log"
_ALL_LOG_LOCK   = threading.Lock()

_SHEET_QUEUE      = collections.deque()
_SHEET_QUEUE_LOCK = threading.Lock()

_CREATED_LOG_TABS      = set()
_CREATED_LOG_TABS_LOCK = threading.Lock()

# ================================================================
# TIMESTAMP HELPERS
# ================================================================
def _ts() -> str:
    return datetime.datetime.now(TZ_JKT).strftime("%H:%M:%S")

def _ts_full() -> str:
    return datetime.datetime.now(TZ_JKT).strftime("%Y-%m-%d %H:%M:%S")

def _get_log_tab() -> str:
    return datetime.datetime.now(TZ_JKT).strftime("%Y-%m-%d")

# ================================================================
# SHEET TAB MANAGEMENT
# ================================================================
def _ensure_log_tab(sheets_svc, tab_name: str):
    with _CREATED_LOG_TABS_LOCK:
        if tab_name in _CREATED_LOG_TABS:
            return
    try:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=LOG_SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=LOG_SPREADSHEET_ID,
            range=f"'{tab_name}'!A1:B1",
            valueInputOption="RAW",
            body={"values": [["Timestamp", "Log"]]},
        ).execute()
    except Exception:
        pass  # Tab already exists — fine
    with _CREATED_LOG_TABS_LOCK:
        _CREATED_LOG_TABS.add(tab_name)

# ================================================================
# WRITE HELPERS — _buf_all is now only used by the stdout/stderr tee
# below (print() calls are rare, so a per-line open/write/close there is
# fine). Every logging.Logger record instead goes through _file_handler,
# a real RotatingFileHandler, which keeps one file descriptor open and
# batches through the stdlib's own lock instead of open()/close()-ing
# bot_all.log on every single log line — that per-line file-open cost,
# multiplied across the dozens of DEBUG-level lines a single Home/Budget
# request used to emit (googleapiclient + apscheduler chief among them),
# was landing directly on request latency.
# ================================================================
def _buf_all(line: str):
    with _ALL_LOG_LOCK:
        try:
            with open(_ALL_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

def _buf_sheet(line: str):
    with _SHEET_QUEUE_LOCK:
        _SHEET_QUEUE.append([_ts_full(), line])

# ================================================================
# BACKGROUND SHEET FLUSHER
# ================================================================
def _sheet_log_flusher():
    while True:
        time.sleep(5)
        with _SHEET_QUEUE_LOCK:
            if not _SHEET_QUEUE:
                continue
            rows = list(_SHEET_QUEUE)
            _SHEET_QUEUE.clear()
        try:
            from google_auth import get_google_services
            _, sheets_svc, _ = get_google_services()
            by_tab = collections.defaultdict(list)
            for row in rows:
                tab = row[0][:10]
                by_tab[tab].append(row)
            for tab_name, tab_rows in by_tab.items():
                _ensure_log_tab(sheets_svc, tab_name)
                sheets_svc.spreadsheets().values().append(
                    spreadsheetId=LOG_SPREADSHEET_ID,
                    range=f"'{tab_name}'!A:B",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": tab_rows},
                ).execute()
        except Exception:
            with _SHEET_QUEUE_LOCK:
                _SHEET_QUEUE.extendleft(reversed(rows))

# ================================================================
# LOGGING HANDLERS
# ================================================================
class _JktLineFormatter(logging.Formatter):
    """Reproduces the historical [HH:MM:SS] LEVEL name: msg shape (Asia/
    Jakarta clock, not the server's local time) so get_all_logs() and the
    /logs viewer don't need to change."""
    def format(self, record):
        base_message = logging.Formatter.format(self, record)
        return "[" + _ts() + "] " + record.levelname + " " + record.name + ": " + base_message

_file_handler = logging.handlers.RotatingFileHandler(
    _ALL_LOG_FILE, maxBytes=5_000_000, backupCount=2, encoding="utf-8",
)
_file_handler.setFormatter(_JktLineFormatter("%(message)s"))

class _SheetQueueHandler(logging.Handler):
    """Enqueues for the background Sheets flusher only -- file writing for
    these same records happens via _file_handler, attached alongside this
    one on the same loggers."""
    def emit(self, record):
        try:
            rendered = logging.Handler.format(self, record)
            line = "[" + _ts() + "] " + record.levelname + " " + record.name + ": " + rendered
            _buf_sheet(line)
        except Exception:
            pass

_sheet_handler = _SheetQueueHandler()
_sheet_handler.setFormatter(logging.Formatter("%(message)s"))

# ================================================================
# STDOUT/STDERR TEE
# ================================================================
class _TeeStream:
    def __init__(self, original):
        self._orig = original
    def write(self, text):
        self._orig.write(text)
        stripped = text.strip()
        if stripped:
            _buf_all(f"[{_ts()}] {stripped}")
    def flush(self):
        self._orig.flush()
    def __getattr__(self, attr):
        return getattr(self._orig, attr)

# ================================================================
# LOG READERS
# ================================================================
def get_all_logs(n: int = 100) -> str:
    """Browser /logs: read last n lines from bot_all.log."""
    try:
        with _ALL_LOG_LOCK:
            with open(_ALL_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        recent = [l.rstrip("\n") for l in lines[-n:]]
        return "\n".join(recent) if recent else "No logs yet."
    except FileNotFoundError:
        return "No logs yet."
    except Exception as e:
        return f"Error reading logs: {e}"

def get_recent_logs(n: int = 20) -> str:
    """WhatsApp /logs command: read last n rows from today's daily sheet tab."""
    try:
        from google_auth import get_google_services
        _, sheets_svc, _ = get_google_services()
        tab_name = _get_log_tab()
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=LOG_SPREADSHEET_ID,
            range=f"'{tab_name}'!A:B",
        ).execute()
        rows = result.get("values", [])
        if rows and rows[0][0].lower() in ("timestamp", "time", "ts"):
            rows = rows[1:]
        if not rows:
            return f"No logs yet for {tab_name}."
        recent = rows[-n:]
        lines = []
        for r in recent:
            entry = f"[{r[0]}] {r[1] if len(r) > 1 else ''}"
            if "| body:" in entry:
                entry = entry[:entry.index("| body:")].rstrip()
            lines.append(entry)
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading logs from Sheet: {e}"

# Loggers that were the dominant source of bot_all.log's 84,985 lines /
# 13 MB at DEBUG: googleapiclient.discovery alone was 22,338 lines,
# apscheduler (executors + scheduler) 31,428, httpcore 1,548. None of
# that is useful day to day, and none of it was free to write — pin them
# above their default noise floor explicitly, rather than relying on
# root's level alone, in case any of these ever sets its own logger
# level (some libraries do).
_NOISY_LOGGERS = ("googleapiclient", "apscheduler", "urllib3", "httpcore", "groq", "google_auth_httplib2")

# ================================================================
# SETUP — call this once at startup
# ================================================================
def setup_logging():
    """Wire up handlers and redirect stdout/stderr.

    bot_all.log is now a RotatingFileHandler (5MB x 2 backups), attached
    ONCE per logger -- never on both a logger and one of its ancestors,
    since with propagate=True (the default) that combination writes every
    line once per handler it passes through on its way up. That bug was
    live before this change: tracer had its own handler AND propagate=True
    up to root's handler (every request-timing line written twice, visible
    as duplicate lines in bot_all.log), and apscheduler.executors.default
    had a directly-attached handler on top of its parent apscheduler
    logger ALSO having one (every scheduler line written up to 3x).

    Root sits at INFO; tracer/httpx are the only loggers with propagate
    disabled, each carrying its own explicit handlers instead."""
    root = logging.getLogger()
    root.addHandler(_file_handler)
    root.setLevel(logging.INFO)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("werkzeug").setLevel(logging.INFO)

    tracer_logger = logging.getLogger("tracer")
    tracer_logger.addHandler(_file_handler)
    tracer_logger.addHandler(_sheet_handler)
    tracer_logger.setLevel(logging.INFO)
    tracer_logger.propagate = False

    httpx_logger = logging.getLogger("httpx")
    httpx_logger.addHandler(_file_handler)
    httpx_logger.addHandler(_sheet_handler)
    httpx_logger.setLevel(logging.INFO)
    httpx_logger.propagate = False

    sys.stdout = _TeeStream(sys.stdout)
    sys.stderr = _TeeStream(sys.stderr)

    threading.Thread(target=_sheet_log_flusher, daemon=True, name="sheet-log-flusher").start()
