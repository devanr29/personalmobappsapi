from config import now_jkt, SPREADSHEET_ID, MAX_LIST_ITEMS
from db import db_conn
from google_auth import get_google_services
from features.memory import save_embedding, delete_embedding, update_embedding
from features.utils import slice_data_rows, has_header_row
from tracer import trace, logger

# ================================================================
# SAVE
# ================================================================
@trace
def save_idea(text: str) -> str:
    conn      = db_conn()
    cursor    = conn.execute(
        "INSERT INTO ideas (content, timestamp) VALUES (?, ?)",
        (text, str(now_jkt()))
    )
    source_id = cursor.lastrowid
    conn.commit()
    conn.close()

    save_embedding("idea", source_id, text)

    try:
        timestamp = now_jkt().strftime("%Y-%m-%d %H:%M")
        _, sheets_svc, _ = get_google_services()
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Ideas!A2:B",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[timestamp, text]]},
        ).execute()
        return "💡 Idea saved!\n📊 Also added to Google Sheets.\n🧠 Memorized for semantic search."
    except Exception as e:
        logger.warning(f"save_idea Sheets sync failed: {e}")
        return f"💡 Idea saved locally.\n🧠 Memorized for semantic search.\n⚠️ Sheets sync failed: {str(e)}"

# ================================================================
# GET
# ================================================================
@trace
def get_ideas(range_start=None, range_end=None, count=None, range_all=False) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        result    = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Ideas!A:B"
        ).execute()
        rows      = result.get("values", [])
        data_rows = [r for r in rows if len(r) >= 2]
        if not data_rows:
            return "💡 No ideas saved yet."
        sliced, offset = slice_data_rows(data_rows, range_start, range_end, count, range_all)
        total  = len(data_rows)
        header = f"💡 *Your ideas* (showing {offset+1}–{offset+len(sliced)} of {total}):"
        lines  = [header, ""]
        for i, r in enumerate(sliced):
            lines.append(f"{offset + i + 1}. {r[1]} _({r[0]})_")
        if range_all and total > MAX_LIST_ITEMS:
            lines.append(
                f"\n_⚠️ Showing last {MAX_LIST_ITEMS} of {total} ideas (display limit). "
                f"Use \"list ideas N-M\" for a specific range._"
            )
        return "\n".join(lines)
    except Exception:
        conn = db_conn()
        rows = conn.execute("SELECT content, timestamp FROM ideas ORDER BY id DESC LIMIT 10").fetchall()
        conn.close()
        if not rows:
            return "💡 No ideas saved yet."
        return "💡 *Your ideas:*\n\n" + "\n".join(
            [f"{i+1}. {r[0]} _({r[1][:10]})_" for i, r in enumerate(rows)]
        )

# ================================================================
# STRUCTURED — list[dict] shape for the mobile REST API. Index-based
# (no stable id in Sheets) — mobile must refetch after any mutation.
# ================================================================
@trace
def get_ideas_structured(range_start=None, range_end=None, count=None, range_all=False) -> list[dict]:
    try:
        _, sheets_svc, _ = get_google_services()
        result    = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Ideas!A:B"
        ).execute()
        rows      = result.get("values", [])
        data_rows = [r for r in rows if len(r) >= 2]
        if not data_rows:
            return []
        sliced, offset = slice_data_rows(data_rows, range_start, range_end, count, range_all)
        return [{"index": offset + i + 1, "content": r[1], "timestamp": r[0]} for i, r in enumerate(sliced)]
    except Exception as e:
        logger.warning(f"get_ideas_structured failed: {e}")
        return []

# ================================================================
# DELETE
# ================================================================
@trace
def delete_idea(keyword: str = None, index: int = None) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        result    = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Ideas!A:B"
        ).execute()
        rows      = result.get("values", [])
        data_rows = [r for r in rows if len(r) >= 2]
        if not data_rows:
            return "💡 No ideas to delete."

        target_i = None
        if index is not None:
            i = int(index) - 1
            if 0 <= i < len(data_rows):
                target_i = i
        elif keyword:
            for i, r in enumerate(data_rows):
                if keyword.lower() in r[1].lower():
                    target_i = i
                    break

        if target_i is None:
            return "❌ Idea not found. Use *get ideas* to see your list."

        deleted_text  = data_rows[target_i][1]
        header_offset = 1 if has_header_row(rows) else 0
        sheet_row     = target_i + 1 + header_offset

        sheet_meta     = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        ideas_sheet_id = next(
            (s["properties"]["sheetId"] for s in sheet_meta["sheets"] if s["properties"]["title"] == "Ideas"),
            None
        )
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"deleteDimension": {"range": {
                "sheetId": ideas_sheet_id, "dimension": "ROWS",
                "startIndex": sheet_row - 1, "endIndex": sheet_row,
            }}}]},
        ).execute()

        conn = db_conn()
        row  = conn.execute(
            "SELECT id FROM ideas WHERE content = ? ORDER BY id LIMIT 1", (deleted_text,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM ideas WHERE id = ?", (row[0],))
            conn.commit()
        conn.close()
        if row:
            delete_embedding("idea", row[0])
        return f"🗑️ Idea deleted: _{deleted_text[:60]}_"
    except Exception as e:
        logger.warning(f"delete_idea failed: {e}")
        return f"⚠️ Could not delete idea: {e}"

# ================================================================
# EDIT
# ================================================================
@trace
def edit_idea(new_content: str, keyword: str = None, index: int = None) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        result    = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Ideas!A:B"
        ).execute()
        rows      = result.get("values", [])
        data_rows = [r for r in rows if len(r) >= 2]
        if not data_rows:
            return "💡 No ideas to edit."

        target_i = None
        if index is not None:
            i = int(index) - 1
            if 0 <= i < len(data_rows):
                target_i = i
        elif keyword:
            for i, r in enumerate(data_rows):
                if keyword.lower() in r[1].lower():
                    target_i = i
                    break

        if target_i is None:
            return "❌ Idea not found. Use *get ideas* to see your list."

        header_offset = 1 if has_header_row(rows) else 0
        sheet_row     = target_i + 1 + header_offset
        timestamp     = now_jkt().strftime("%Y-%m-%d %H:%M")

        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"Ideas!A{sheet_row}:B{sheet_row}",
            valueInputOption="RAW",
            body={"values": [[timestamp, new_content]]},
        ).execute()

        old_text = data_rows[target_i][1]
        conn = db_conn()
        row  = conn.execute(
            "SELECT id FROM ideas WHERE content = ? ORDER BY id LIMIT 1", (old_text,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE ideas SET content=?, timestamp=? WHERE id=?",
                (new_content, str(now_jkt()), row[0])
            )
            conn.commit()
        conn.close()
        if row:
            update_embedding("idea", row[0], new_content)
        return f"✏️ Idea updated!\n_{new_content[:80]}_"
    except Exception as e:
        logger.warning(f"edit_idea failed: {e}")
        return f"⚠️ Could not edit idea: {e}"
