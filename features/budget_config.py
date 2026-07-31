import re, json
from config import now_jkt, SPREADSHEET_ID, FIXED_EXPENSES, VARIABLE_BUDGETS
from google_auth import get_google_services
from ai.groq_client import groq_complete
from tracer import trace

_FIXED_RANGE    = "Fixed Expenses!A:C"
_VARIABLE_RANGE = "Variable Budgets!A:B"
_FIXED_APPEND   = "Fixed Expenses!A2:C"
_VARIABLE_APPEND = "Variable Budgets!A2:B"

# ================================================================
# ROW PARSERS  (skips header row by checking if col B is numeric)
# ================================================================
def _parse_fixed_rows(rows: list) -> list[dict]:
    out = []
    for r in rows:
        if not r or len(r) < 2:
            continue
        try:
            amount = int(r[1])
        except (ValueError, TypeError):
            continue  # header or malformed — skip
        due_day = None
        if len(r) >= 3 and r[2]:
            try:
                due_day = int(r[2])
            except (ValueError, TypeError):
                pass
        out.append({"name": r[0], "amount": amount, "due_day": due_day})
    return out

def _parse_variable_rows(rows: list) -> list[dict]:
    out = []
    for r in rows:
        if not r or len(r) < 2:
            continue
        try:
            budget = int(r[1])
        except (ValueError, TypeError):
            continue
        out.append({"name": r[0], "budget": budget})
    return out

# ================================================================
# SHEET HELPERS
# ================================================================
def _get_sheet_id(sheets_svc, title: str) -> int | None:
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None

def _delete_row(sheets_svc, sheet_title: str, sheet_row_1based: int):
    sid = _get_sheet_id(sheets_svc, sheet_title)
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"deleteDimension": {"range": {
            "sheetId": sid, "dimension": "ROWS",
            "startIndex": sheet_row_1based - 1, "endIndex": sheet_row_1based,
        }}}]},
    ).execute()

def _find_fixed_row(sheets_svc, name: str):
    """Returns (row_dict, 1-based row index) or (None, None)."""
    rows = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=_FIXED_RANGE
    ).execute().get("values", [])
    needle = name.lower()
    for i, r in enumerate(rows):
        if not r or len(r) < 2:
            continue
        try:
            amount = int(r[1])
        except (ValueError, TypeError):
            continue
        row_name = r[0].lower()
        if needle in row_name or row_name in needle:
            due_day = None
            if len(r) >= 3 and r[2]:
                try:
                    due_day = int(r[2])
                except (ValueError, TypeError):
                    pass
            return {"name": r[0], "amount": amount, "due_day": due_day}, i + 1
    return None, None

def _find_variable_row(sheets_svc, name: str):
    """Returns (row_dict, 1-based row index) or (None, None)."""
    rows = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=_VARIABLE_RANGE
    ).execute().get("values", [])
    needle = name.lower()
    for i, r in enumerate(rows):
        if not r or len(r) < 2:
            continue
        try:
            budget = int(r[1])
        except (ValueError, TypeError):
            continue
        row_name = r[0].lower()
        if needle in row_name or row_name in needle:
            return {"name": r[0], "budget": budget}, i + 1
    return None, None

def _seed_if_empty(sheets_svc, rows: list, tab: str):
    """Write header + defaults to an empty sheet tab."""
    if rows:
        return
    if tab == "Fixed Expenses":
        header = [["Name", "Amount", "Due Day"]]
        data   = [[e["name"], e["amount"], e.get("due_day") or ""] for e in FIXED_EXPENSES]
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range=_FIXED_APPEND,
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": header + data},
        ).execute()
    else:
        header = [["Name", "Budget"]]
        data   = [[v["name"], v["budget"]] for v in VARIABLE_BUDGETS]
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range=_VARIABLE_APPEND,
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": header + data},
        ).execute()

# ================================================================
# PUBLIC READ
# ================================================================
def get_fixed_expenses() -> list[dict]:
    try:
        _, sheets_svc, _ = get_google_services()
        rows = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=_FIXED_RANGE
        ).execute().get("values", [])
        parsed = _parse_fixed_rows(rows)
        if not parsed:
            _seed_if_empty(sheets_svc, parsed, "Fixed Expenses")
            rows = sheets_svc.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=_FIXED_RANGE
            ).execute().get("values", [])
            parsed = _parse_fixed_rows(rows)
        return parsed
    except Exception as e:
        print(f"[BudgetConfig] get_fixed_expenses error: {e}")
        return [dict(e) for e in FIXED_EXPENSES]

def get_variable_budgets() -> list[dict]:
    try:
        _, sheets_svc, _ = get_google_services()
        rows = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=_VARIABLE_RANGE
        ).execute().get("values", [])
        parsed = _parse_variable_rows(rows)
        if not parsed:
            _seed_if_empty(sheets_svc, parsed, "Variable Budgets")
            rows = sheets_svc.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=_VARIABLE_RANGE
            ).execute().get("values", [])
            parsed = _parse_variable_rows(rows)
        return parsed
    except Exception as e:
        print(f"[BudgetConfig] get_variable_budgets error: {e}")
        return [dict(v) for v in VARIABLE_BUDGETS]

# ================================================================
# CRUD — FIXED EXPENSES
# ================================================================
def add_fixed_expense(name: str, amount: int, due_day: int | None = None) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range=_FIXED_APPEND,
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": [[name, amount, due_day or ""]]},
        ).execute()
        due = f" (due on the {due_day}th)" if due_day else ""
        return f"✅ Fixed expense *{name}* — Rp {amount:,}{due} added.".replace(",", ".")
    except Exception as e:
        return f"⚠️ Could not add fixed expense: {e}"

def remove_fixed_expense(name: str) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        exp, row = _find_fixed_row(sheets_svc, name)
        if not exp:
            return f"❌ No fixed expense matching *{name}* found."
        _delete_row(sheets_svc, "Fixed Expenses", row)
        return f"🗑️ Fixed expense *{exp['name']}* removed."
    except Exception as e:
        return f"⚠️ Could not remove fixed expense: {e}"

def edit_fixed_expense(name: str, new_name: str | None = None,
                       new_amount: int | None = None, new_due_day=...) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        exp, row = _find_fixed_row(sheets_svc, name)
        if not exp:
            return f"❌ No fixed expense matching *{name}* found."
        updated_name    = new_name    if new_name    is not None else exp["name"]
        updated_amount  = new_amount  if new_amount  is not None else exp["amount"]
        updated_due_day = new_due_day if new_due_day is not ...  else exp["due_day"]
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"Fixed Expenses!A{row}:C{row}",
            valueInputOption="RAW",
            body={"values": [[updated_name, updated_amount, updated_due_day or ""]]},
        ).execute()
        due = f" (due on the {updated_due_day}th)" if updated_due_day else ""
        return f"✏️ Fixed expense updated: *{updated_name}* — Rp {updated_amount:,}{due}.".replace(",", ".")
    except Exception as e:
        return f"⚠️ Could not edit fixed expense: {e}"

# ================================================================
# CRUD — VARIABLE BUDGETS
# ================================================================
def add_variable_budget(name: str, budget: int) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        sheets_svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range=_VARIABLE_APPEND,
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": [[name, budget]]},
        ).execute()
        return f"✅ Variable budget *{name}* — Rp {budget:,} added.".replace(",", ".")
    except Exception as e:
        return f"⚠️ Could not add variable budget: {e}"

def remove_variable_budget(name: str) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        var, row = _find_variable_row(sheets_svc, name)
        if not var:
            return f"❌ No variable budget matching *{name}* found."
        _delete_row(sheets_svc, "Variable Budgets", row)
        return f"🗑️ Variable budget *{var['name']}* removed."
    except Exception as e:
        return f"⚠️ Could not remove variable budget: {e}"

def edit_variable_budget(name: str, new_name: str | None = None, new_budget: int | None = None) -> str:
    try:
        _, sheets_svc, _ = get_google_services()
        var, row = _find_variable_row(sheets_svc, name)
        if not var:
            return f"❌ No variable budget matching *{name}* found."
        updated_name   = new_name   if new_name   is not None else var["name"]
        updated_budget = new_budget if new_budget is not None else var["budget"]
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"Variable Budgets!A{row}:B{row}",
            valueInputOption="RAW",
            body={"values": [[updated_name, updated_budget]]},
        ).execute()
        return f"✏️ Variable budget updated: *{updated_name}* — Rp {updated_budget:,}.".replace(",", ".")
    except Exception as e:
        return f"⚠️ Could not edit variable budget: {e}"

# ================================================================
# LIST
# ================================================================
def list_budget_config() -> str:
    fixed    = get_fixed_expenses()
    variable = get_variable_budgets()

    lines = ["⚙️ *Budget Configuration*\n"]
    lines.append("📋 *Fixed Expenses:*")
    if fixed:
        for e in fixed:
            due = f" (due {e['due_day']}th)" if e["due_day"] else " (no fixed date)"
            lines.append(f"  • {e['name']}: Rp {e['amount']:,}{due}".replace(",", "."))
        total = sum(e["amount"] for e in fixed)
        lines.append(f"  ➤ Total: Rp {total:,}".replace(",", "."))
    else:
        lines.append("  (none)")

    lines.append("\n🗂️ *Variable Budgets:*")
    if variable:
        for v in variable:
            lines.append(f"  • {v['name']}: Rp {v['budget']:,}".replace(",", "."))
        total = sum(v["budget"] for v in variable)
        lines.append(f"  ➤ Total: Rp {total:,}".replace(",", "."))
    else:
        lines.append("  (none)")

    lines.append("\n💡 You can say:")
    lines.append('  "add fixed Gym 200000 due 1"')
    lines.append('  "add variable Coffee 100000"')
    lines.append('  "edit fixed Internet to 175000"')
    lines.append('  "remove fixed House Maintenance"')
    lines.append('  "remove variable Laundry"')
    return "\n".join(lines)

# ================================================================
# AI COMMAND PARSER
# ================================================================
@trace
def _parse_config_command(user_input: str) -> dict | None:
    prompt = f"""Parse this budget configuration command and return JSON.

Possible actions:
- "list": user wants to view/show/list current budget configuration
- "add_fixed": add a new fixed monthly expense
- "add_variable": add a new variable budget category
- "edit_fixed": edit an existing fixed expense (name, amount, or due_day)
- "edit_variable": edit an existing variable budget (name or budget amount)
- "remove_fixed": delete/remove a fixed expense
- "remove_variable": delete/remove a variable budget category

Reply ONLY with valid JSON, no markdown:
{{"action": "<list|add_fixed|add_variable|edit_fixed|edit_variable|remove_fixed|remove_variable>", "name": "<current name or null>", "amount": <integer IDR or null>, "due_day": <1-31 or null>, "new_name": "<new name if renaming or null>", "new_amount": <new integer IDR if changing amount or null>, "new_due_day": <new due day if changing or null>}}

User message: {user_input}"""

    try:
        raw = groq_complete(
            system_prompt="You are a command parser. Reply with valid JSON only.",
            user_prompt=prompt,
            max_tokens=200,
            temperature=0.0,
        )
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[BudgetConfig parse error] {e}")
        return None

# ================================================================
# MAIN HANDLER
# ================================================================
@trace
def handle_budget_config(user_input: str) -> str:
    bare_triggers = {"budget config", "lihat budget config", "show budget config",
                     "budget setup", "lihat budget", "budget settings"}
    if user_input.strip().lower() in bare_triggers:
        return list_budget_config()

    cmd = _parse_config_command(user_input)
    if not cmd:
        return list_budget_config()

    action = cmd.get("action", "list")

    if action == "list":
        return list_budget_config()

    elif action == "add_fixed":
        name   = cmd.get("name")
        amount = cmd.get("amount")
        if not name or not amount:
            return "❌ Please specify a name and amount. Example: \"add fixed Gym 200000 due 1\""
        return add_fixed_expense(name, int(amount), cmd.get("due_day"))

    elif action == "add_variable":
        name   = cmd.get("name")
        amount = cmd.get("amount")
        if not name or not amount:
            return "❌ Please specify a name and amount. Example: \"add variable Coffee 100000\""
        return add_variable_budget(name, int(amount))

    elif action == "edit_fixed":
        name = cmd.get("name")
        if not name:
            return "❌ Please specify which fixed expense to edit."
        new_due = cmd.get("new_due_day", ...)
        return edit_fixed_expense(
            name,
            new_name=cmd.get("new_name"),
            new_amount=int(cmd["new_amount"]) if cmd.get("new_amount") else None,
            new_due_day=new_due,
        )

    elif action == "edit_variable":
        name = cmd.get("name")
        if not name:
            return "❌ Please specify which variable budget to edit."
        return edit_variable_budget(
            name,
            new_name=cmd.get("new_name"),
            new_budget=int(cmd["new_amount"]) if cmd.get("new_amount") else None,
        )

    elif action == "remove_fixed":
        name = cmd.get("name")
        if not name:
            return "❌ Please specify which fixed expense to remove."
        return remove_fixed_expense(name)

    elif action == "remove_variable":
        name = cmd.get("name")
        if not name:
            return "❌ Please specify which variable budget to remove."
        return remove_variable_budget(name)

    return list_budget_config()
