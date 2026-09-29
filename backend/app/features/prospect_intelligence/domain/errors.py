"""Expected prospect-intelligence business failures."""

from app.shared_kernel.errors import DomainError


class InvalidRunTransitionError(DomainError):
    """Raised when a run cannot accept the requested state transition."""


class UnsafeOutreachError(DomainError):
    """Raised when customer outreach contains internal-only business data."""
