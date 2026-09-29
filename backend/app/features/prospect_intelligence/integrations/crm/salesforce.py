"""Salesforce CRM adapter shell."""

from ...contracts.models import Account
from ...contracts.sources import SourceCallContext, SourceResult


class SalesforceCrmSource:
    """Salesforce adapter used in production once auth, mapping, and paging are finalized."""

    def get_account(self, context: SourceCallContext, account_id: str) -> SourceResult[Account]:
        del context, account_id
        raise NotImplementedError("production Salesforce CRM integration is not finalized")
