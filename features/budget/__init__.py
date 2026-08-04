"""Budget feature package. Exposes only the Flask blueprint — the ledger
is managed exclusively through the Budget tab's REST API. Chat reads the
ledger via features.budget.service (read-only) and formats it through
features.budget.chat_view; neither of those needs a package-level
re-export."""
from features.budget.blueprint import budget_bp

__all__ = ["budget_bp"]
