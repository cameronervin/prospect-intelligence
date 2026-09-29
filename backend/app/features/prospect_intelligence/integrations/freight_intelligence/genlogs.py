"""GenLogs freight-intelligence adapter shell."""

from ...contracts.models import Account
from ...contracts.sources import FreightActivity, SourceCallContext, SourceResult


class GenLogsFreightIntelligenceSource:
    """GenLogs adapter used in production.

    Finalize authentication, schemas, quotas, and licensing before wiring it.
    """

    def get_activity(
        self, context: SourceCallContext, account: Account
    ) -> SourceResult[FreightActivity]:
        del context, account
        raise NotImplementedError("production GenLogs integration is not finalized")
