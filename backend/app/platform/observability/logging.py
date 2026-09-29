"""Structured logging with conservative key-based redaction."""

import logging
from typing import cast

import structlog
from structlog.types import EventDict, Processor

_SENSITIVE_MARKERS = ("authorization", "cookie", "password", "secret", "token", "api_key")


def _is_sensitive(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return {
            str(key): "[REDACTED]" if _is_sensitive(str(key)) else _redact_value(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in cast(tuple[object, ...], value))
    return value


def redact_sensitive_values(
    _logger: object,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Redact values whose keys indicate credential material."""

    return cast(EventDict, _redact_value(dict(event_dict)))


def configure_logging(*, level: str, json_output: bool) -> None:
    """Configure standard logging and structlog once per app creation."""

    logging.basicConfig(level=level, format="%(message)s", force=True)
    # HTTPX includes complete query strings in its INFO request log. Provider credentials such as
    # FMCSA WebKey are required query parameters, so application logging must never emit that line.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive_values,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL,
            }[level]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
