"""Typed, non-sensitive HTTP error contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_ERROR = "internal_error"


class ErrorIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    message: str
    type: str


def _empty_issues() -> list[ErrorIssue]:
    return []


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ApiErrorCode
    message: str
    retryable: bool
    issues: list[ErrorIssue] = Field(default_factory=_empty_issues)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
