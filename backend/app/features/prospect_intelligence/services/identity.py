"""Identity conversion at durable service and worker boundaries."""

from app.features.authentication.public import AuthContext, UserRole

from ..contracts.models import ProspectRun


def persisted_auth(run: ProspectRun) -> AuthContext:
    return AuthContext(
        subject=run.created_by_subject,
        tenant_id=run.tenant_id,
        rep_id=run.rep_id,
        roles=frozenset(UserRole(role) for role in run.created_by_roles),
    )


def require_run_scope(
    run: ProspectRun,
    auth: AuthContext,
) -> ProspectRun:
    if (
        run.tenant_id != auth.tenant_id
        or run.rep_id != auth.rep_id
        or run.created_by_subject != auth.subject
    ):
        raise LookupError(f"unknown run: {run.id}")
    return run
