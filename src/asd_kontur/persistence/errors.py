"""Typed persistence boundary failures."""


class PersistenceError(RuntimeError):
    """Base class for persistence foundation failures."""


class ScopeRequiredError(PersistenceError):
    """A scoped repository was requested without the required context."""


class OptimisticConcurrencyError(PersistenceError):
    """The expected aggregate revision is stale."""


class IdempotencyConflictError(PersistenceError):
    """The same scoped idempotency key was reused with different semantics."""
