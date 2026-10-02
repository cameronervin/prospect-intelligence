"""Actor-scoped outreach validation context construction."""

from ..contracts import repositories
from ..contracts.models import ProspectRun
from ..domain.outreach import OutreachContext, outreach_context


def build_outreach_validation_context(
    accounts: repositories.AccountRepository,
    run: ProspectRun,
) -> OutreachContext:
    assigned_accounts = accounts.list_for_actor(
        run.tenant_id,
        run.created_by_subject,
        run.rep_id,
    )
    return outreach_context(
        run,
        assigned_account_names=tuple(account.name for account in assigned_accounts),
    )
