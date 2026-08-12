"""Typed errors for the budget blueprint — raised by service-layer code and
mapped to the standard {error:{code,message},meta} envelope by one
errorhandler in blueprint.py, replacing the emoji-prefix status sniffing
still used by the legacy Sheets-backed config routes."""


class BudgetError(Exception):
    code = "BUDGET_ERROR"
    status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BudgetNotFound(BudgetError):
    code = "NOT_FOUND"
    status = 404


class BudgetValidationError(BudgetError):
    code = "VALIDATION_ERROR"
    status = 400


class BudgetConflict(BudgetError):
    code = "CONFLICT"
    status = 409


# ================================================================
# Wallet by BudgetBakers sync errors (features/budget/wallet/) — same
# BudgetError base so the existing @budget_bp.errorhandler(BudgetError)
# maps them to the standard envelope for free.
# ================================================================
class WalletNotConfigured(BudgetError):
    code = "WALLET_NOT_CONFIGURED"
    status = 503


class WalletTokenExpired(BudgetError):
    code = "WALLET_TOKEN_EXPIRED"
    status = 401


class WalletInitSyncInProgress(BudgetError):
    code = "WALLET_INIT_SYNC_IN_PROGRESS"
    status = 409


class WalletRateLimited(BudgetError):
    code = "WALLET_RATE_LIMITED"
    status = 429


class WalletRequestError(BudgetError):
    """Any Wallet API failure that isn't one of the specific cases above
    (4xx validation error, 5xx on their end, network failure). Carries the
    vendor's response body verbatim in .message so a preview/dry-run
    surfaces exactly what Wallet rejected, rather than a generic 502."""
    code = "WALLET_REQUEST_ERROR"
    status = 502
