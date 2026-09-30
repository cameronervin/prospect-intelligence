"""Validated projections from compiled graph artifacts into product contracts."""

from collections.abc import Mapping
from typing import cast

from app.features.prospect_intelligence.contracts.models import OutreachDraft
from app.features.prospect_intelligence.contracts.sources import (
    INJECTION_CANARY_CACHE_KEY,
    SourceCallContext,
)


def checkpoint_files(values: Mapping[str, object]) -> Mapping[str, object]:
    files = values.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("compiled graph checkpoint contains no artifact filesystem")
    raw_files = cast("Mapping[object, object]", files)
    return {str(path): value for path, value in raw_files.items()}


def injection_canary(context: SourceCallContext) -> str | None:
    value = context.cache.get(INJECTION_CANARY_CACHE_KEY)
    return value if isinstance(value, str) and value else None


def text_file(files: Mapping[str, object], path: str) -> str:
    raw = files.get(path)
    if not isinstance(raw, Mapping):
        raise ValueError(f"compiled graph omitted required artifact: {path}")
    file = dict(cast("Mapping[object, object]", raw))
    content = file.get("content")
    if file.get("encoding") != "utf-8" or not isinstance(content, str) or not content.strip():
        raise ValueError(f"compiled graph returned invalid artifact: {path}")
    return content.strip()


def parse_outreach(content: str) -> OutreachDraft:
    subject_line, separator, body = content.partition("\n")
    if not separator or not subject_line.startswith("Subject: ") or not body.strip():
        raise ValueError("compiled graph returned an invalid outreach draft")
    return OutreachDraft(
        subject=subject_line.removeprefix("Subject: ").strip(),
        body=body.strip(),
    )
