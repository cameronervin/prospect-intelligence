"""Structured logging with conservative key-based redaction."""

import logging
import sys
from typing import cast

import structlog
from structlog.types import EventDict, Processor

_SENSITIVE_MARKERS = ("authorization", "cookie", "password", "secret", "token", "api_key")


class _CurrentStdout:
    """Resolve stdout at write time so test capture streams cannot become stale."""

    def write(self, value: str) -> int:
        return sys.stdout.write(value)

    def flush(self) -> None:
        sys.stdout.flush()


def _is_sensitive(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


def _redact_value(value: object) -> object:
    if isinstance(value, BaseException):
        return type(value).__name__
    if isinstance(value, str):
        return value.replace("\r", "\\r").replace("\n", "\\n")
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


def sanitize_exception_details(
    _logger: object,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Retain exception classification without serializing messages or tracebacks."""

    exc_info = event_dict.pop("exc_info", None)
    for key in ("exc_text", "exception", "stack", "stack_info"):
        event_dict.pop(key, None)
    if isinstance(exc_info, tuple) and exc_info:
        exception_parts = cast(tuple[object, ...], exc_info)
        error_type = getattr(exception_parts[0], "__name__", None)
        if isinstance(error_type, str):
            event_dict.setdefault("error_type", error_type)
    return event_dict


def configure_logging(
    *,
    level: str,
    json_output: bool,
    service: str = "langchain-takehome-backend",
    environment: str = "development",
) -> None:
    """Configure one structured stdout pipeline for application and dependency logs."""

    numeric_level = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }[level]

    def add_service_context(
        _logger: object,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict.setdefault("service", service)
        event_dict.setdefault("environment", environment)
        return event_dict

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        add_service_context,
        sanitize_exception_details,
        redact_sensitive_values,
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ExtraAdder(),
            timestamper,
            add_service_context,
            redact_sensitive_values,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            sanitize_exception_details,
            redact_sensitive_values,
            renderer,
        ],
    )
    handler = logging.StreamHandler(_CurrentStdout())
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # HTTPX includes complete query strings in its INFO request log. Provider credentials such as
    # FMCSA WebKey are required query parameters, so application logging must never emit that line.
    for logger_name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # The application emits a safer canonical request line without paths, query strings, or peers.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
    for logger_name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.disabled = False
        uvicorn_logger.setLevel(numeric_level)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Application factories are created repeatedly in tests; keep lazy proxies reconfigurable.
        cache_logger_on_first_use=False,
    )
