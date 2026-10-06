"""Actor-scoped outreach validation context construction."""

from ..contracts import repositories
from ..contracts.models import ProspectRun
from ..domain.outreach import OutreachContext, outreach_context


def assigned_other_account_names(
    accounts: repositories.AccountRepository,
    run: ProspectRun,
) -> tuple[str, ...]:
    """Return actor-scoped account names except the selected account, without needing analysis."""

    selected = run.account.name.strip().casefold()
    return tuple(
        account.name
        for account in accounts.list_for_actor(
            run.tenant_id,
            run.created_by_subject,
            run.rep_id,
        )
        if account.name.strip().casefold() != selected
    )


def build_outreach_validation_context(
    accounts: repositories.AccountRepository,
    run: ProspectRun,
) -> OutreachContext:
    return outreach_context(
        run,
        assigned_account_names=assigned_other_account_names(accounts, run),
    )


class OutreachScopeAccess:
    """Actor-scoped account-name access shared by run and agent services."""

    _accounts: repositories.AccountRepository

    def outreach_validation_context(self, run: ProspectRun) -> OutreachContext:
        return build_outreach_validation_context(self._accounts, run)

    def other_account_names(self, run: ProspectRun) -> tuple[str, ...]:
        return assigned_other_account_names(self._accounts, run)
