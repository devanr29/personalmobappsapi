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
