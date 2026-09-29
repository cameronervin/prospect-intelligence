"""Carrier TMS network adapter shell."""

from ...contracts.sources import CarrierNetwork, SourceCallContext, SourceResult


class TmsCarrierNetworkSource:
    """Carrier TMS adapter used in production once auth, mapping, and tenancy are finalized."""

    def get_network(self, context: SourceCallContext) -> SourceResult[CarrierNetwork]:
        del context
        raise NotImplementedError("production carrier-network integration is not finalized")
