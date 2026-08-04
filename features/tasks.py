from googleapiclient.errors import HttpError
from config import now_jkt, MAX_LIST_ITEMS
from db import db_conn
from google_auth import get_google_services
from tracer import trace, logger

# ================================================================
# SAVE
# ================================================================
@trace
def save_task(text: str) -> str:
    conn = db_conn()
    conn.execute("INSERT INTO tasks (content, timestamp) VALUES (?, ?)", (text, str(now_jkt())))
    conn.commit()
    conn.close()
    try:
        _, _, tasks_svc = get_google_services()
        tasks_svc.tasks().insert(
            tasklist="@default",
            body={"title": text, "status": "needsAction"},
        ).execute()
        return "✅ Task added!\n📋 Also added to Google Tasks."
    except Exception as e:
        logger.warning(f"save_task Google Tasks sync failed: {e}")
        return f"✅ Task saved locally.\n⚠️ Google Tasks sync failed: {str(e)}"

# ================================================================
# GET
# ================================================================
@trace
def get_tasks(range_start=None, range_end=None, count=None, range_all=False) -> str:
    try:
        _, _, tasks_svc = get_google_services()
        result = tasks_svc.tasks().list(tasklist="@default", showCompleted=False, maxResults=100).execute()
        items  = result.get("items", [])
        if not items:
            return "📋 No pending tasks."
        total = len(items)
        if range_all:
            start  = max(0, total - MAX_LIST_ITEMS)
            sliced = items[start:]
            offset = start
        elif range_start is not None and range_end is not None:
            s      = max(0, int(range_start) - 1)
            e      = min(total, int(range_end))
            sliced = items[s:e]
            offset = s
        elif count is not None:
            n      = min(int(count), MAX_LIST_ITEMS)
            start  = max(0, total - n)
            sliced = items[start:]
            offset = start
        else:
            start  = max(0, total - 10)
            sliced = items[start:]
            offset = start
        header = f"📋 *Your tasks* (showing {offset+1}–{offset+len(sliced)} of {total}):"
        lines  = [header, ""]
        for i, t in enumerate(sliced):
            lines.append(f"{offset + i + 1}. {t['title']}")
        if range_all and total > MAX_LIST_ITEMS:
            lines.append(
                f"\n_⚠️ Showing last {MAX_LIST_ITEMS} of {total} tasks (display limit). "
                f"Use \"list tasks N-M\" for a specific range._"
            )
        return "\n".join(lines)
    except Exception:
        conn = db_conn()
        rows = conn.execute("SELECT content FROM tasks WHERE done=0 ORDER BY id DESC LIMIT 10").fetchall()
        conn.close()
        if not rows:
            return "📋 No pending tasks."
        return "📋 *Your tasks:*\n\n" + "\n".join([f"{i+1}. {r[0]}" for i, r in enumerate(rows)])

# ================================================================
# STRUCTURED — list[dict] shape for the mobile REST API
# ================================================================
@trace
def get_tasks_structured() -> list[dict]:
    try:
        _, _, tasks_svc = get_google_services()
        result = tasks_svc.tasks().list(tasklist="@default", showCompleted=False, maxResults=100).execute()
        items  = result.get("items", [])
        return [
            {"id": t["id"], "title": t.get("title", ""), "status": t.get("status", "needsAction")}
            for t in items
        ]
    except Exception as e:
        logger.warning(f"get_tasks_structured failed: {e}")
        return []

@trace
def complete_task_by_id(task_id: str) -> bool:
    """Id-based complete for the REST API (get_tasks_structured() already
    surfaces the real Google Task id, so no keyword fuzzy-matching needed).
    Returns False if the id doesn't exist; raises on any other failure.
    Google Tasks returns 400 "Invalid task ID" for a malformed/unknown id
    (not 404), so both are treated as "not found" here."""
    try:
        _, _, tasks_svc = get_google_services()
        tasks_svc.tasks().patch(
            tasklist="@default", task=task_id, body={"status": "completed"}
        ).execute()
        return True
    except HttpError as e:
        if e.resp.status in (400, 404):
            return False
        raise

@trace
def delete_task_by_id(task_id: str) -> bool:
    """Id-based delete for the REST API. Returns False if the id doesn't
    exist; raises on any other failure. See complete_task_by_id() for why
    both 400 and 404 are treated as "not found"."""
    try:
        _, _, tasks_svc = get_google_services()
        tasks_svc.tasks().delete(tasklist="@default", task=task_id).execute()
        return True
    except HttpError as e:
        if e.resp.status in (400, 404):
            return False
        raise

# ================================================================
# COMPLETE
# ================================================================
@trace
def complete_task(keyword: str) -> str:
    try:
        _, _, tasks_svc = get_google_services()
        result  = tasks_svc.tasks().list(tasklist="@default", showCompleted=False).execute()
        items   = result.get("items", [])
        matched = [t for t in items if keyword.lower() in t["title"].lower()]
        if not matched:
            return f"❌ No task found matching '{keyword}'."
        t = matched[0]
        tasks_svc.tasks().patch(
            tasklist="@default", task=t["id"], body={"status": "completed"}
        ).execute()
        return f"✅ Task *'{t['title']}'* marked as complete!"
    except Exception as e:
        logger.warning(f"complete_task failed: {e}")
        return f"⚠️ Could not complete task: {str(e)}"

# ================================================================
# DELETE
# ================================================================
@trace
def delete_task(keyword: str = None, index: int = None) -> str:
    try:
        _, _, tasks_svc = get_google_services()
        result = tasks_svc.tasks().list(tasklist="@default", showCompleted=False).execute()
        items  = result.get("items", [])
        if not items:
            return "📋 No tasks to delete."

        target = None
        if index is not None:
            i = int(index) - 1
            if 0 <= i < len(items):
                target = items[i]
        elif keyword:
            for t in items:
                if keyword.lower() in t["title"].lower():
                    target = t
                    break

        if not target:
            return "❌ Task not found. Use *get tasks* to see your list."

        tasks_svc.tasks().delete(tasklist="@default", task=target["id"]).execute()

        conn = db_conn()
        row  = conn.execute(
            "SELECT id FROM tasks WHERE content = ? ORDER BY id LIMIT 1", (target["title"],)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM tasks WHERE id = ?", (row[0],))
            conn.commit()
        conn.close()
        return f"🗑️ Task deleted: _{target['title']}_"
    except Exception as e:
        logger.warning(f"delete_task failed: {e}")
        return f"⚠️ Could not delete task: {e}"

# ================================================================
# EDIT
# ================================================================
@trace
def edit_task(new_title: str, keyword: str = None, index: int = None) -> str:
    try:
        _, _, tasks_svc = get_google_services()
        result = tasks_svc.tasks().list(tasklist="@default", showCompleted=False).execute()
        items  = result.get("items", [])
        if not items:
            return "📋 No tasks to edit."

        target = None
        if index is not None:
            i = int(index) - 1
            if 0 <= i < len(items):
                target = items[i]
        elif keyword:
            for t in items:
                if keyword.lower() in t["title"].lower():
                    target = t
                    break

        if not target:
            return "❌ Task not found. Use *get tasks* to see your list."

        tasks_svc.tasks().patch(
            tasklist="@default", task=target["id"], body={"title": new_title}
        ).execute()

        old_title = target["title"]
        conn = db_conn()
        row  = conn.execute(
            "SELECT id FROM tasks WHERE content = ? ORDER BY id LIMIT 1", (old_title,)
        ).fetchone()
        if row:
            conn.execute("UPDATE tasks SET content=? WHERE id=?", (new_title, row[0]))
            conn.commit()
        conn.close()
        return f"✏️ Task updated!\n_{new_title}_"
    except Exception as e:
        logger.warning(f"edit_task failed: {e}")
        return f"⚠️ Could not edit task: {e}"
