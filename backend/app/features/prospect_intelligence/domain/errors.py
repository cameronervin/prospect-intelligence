"""Expected prospect-intelligence business failures."""

import re
from collections.abc import Sequence

from app.shared_kernel.errors import DomainError


class InvalidRunTransitionError(DomainError):
    """Raised when a run cannot accept the requested state transition."""


class UnsafeOutreachError(DomainError):
    """Raised when customer outreach contains internal-only business data."""


_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


def validate_error_code(code: str) -> str:
    """Reject values that could smuggle private output into logs or the attempt ledger."""

    if _SAFE_CODE.fullmatch(code) is None:
        raise ValueError("error code must be a sanitized snake-case identifier")
    return code


class AgentOutputInvalidError(DomainError):
    """A typed submission may be corrected within its current agent stage."""

    def __init__(self, *issue_codes: str | Sequence[str]) -> None:
        raw_codes: Sequence[str | object]
        if len(issue_codes) == 1 and not isinstance(issue_codes[0], str):
            raw_codes = issue_codes[0]
        else:
            raw_codes = issue_codes
        if not raw_codes:
            raise ValueError("agent output failure requires at least one issue code")
        validated: list[str] = []
        for code in raw_codes:
            if not isinstance(code, str):
                raise ValueError("issue codes must be sanitized snake-case identifiers")
            validated.append(validate_error_code(code))
        self.issue_codes = tuple(validated)
        self.code = self.issue_codes[0]
        super().__init__(self.code)


class AgentOutputExhaustedError(DomainError):
    """The stage exhausted its bounded correction attempts."""

    code = "agent_output_exhausted"

    def __init__(self) -> None:
        super().__init__(self.code)


class ModelUnavailableError(DomainError):
    """Provider retries were exhausted and the worker may resume its checkpoint."""

    code = "model_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)
