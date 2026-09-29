"""Stable, tenant-scoped identities for durable graph state and memory."""

import re
from uuid import UUID

from .filesystem import SCOPE_ID_PATTERN


def checkpoint_thread_id(tenant_id: str, rep_id: str, run_id: UUID) -> str:
    _validate_scope(tenant_id, rep_id)
    return f"prospect:v1:{tenant_id}:{rep_id}:{run_id}"


def preference_namespace(tenant_id: str, rep_id: str) -> tuple[str, ...]:
    _validate_scope(tenant_id, rep_id)
    return ("prospect_intelligence", "v1", tenant_id, rep_id, "preferences")


def _validate_scope(tenant_id: str, rep_id: str) -> None:
    if not re.fullmatch(SCOPE_ID_PATTERN, tenant_id) or not re.fullmatch(SCOPE_ID_PATTERN, rep_id):
        raise ValueError("invalid scope identifier for durable workflow state")
