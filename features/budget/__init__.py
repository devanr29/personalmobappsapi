"""Budget feature package.

Re-exports the chat-facing surface from legacy_chat so intents.py and
ai/tool_executor.py need no changes across this package conversion.
"""
from features.budget.legacy_chat import (
    _budget_interactive_prompt,
    _compute_budget,
    _format_budget,
    calculate_budget,
    compute_and_persist_budget,
)
from features.budget.blueprint import budget_bp

__all__ = [
    "_budget_interactive_prompt",
    "_compute_budget",
    "_format_budget",
    "budget_bp",
    "calculate_budget",
    "compute_and_persist_budget",
]
