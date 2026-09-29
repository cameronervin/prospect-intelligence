"""CRM source adapters."""

from .salesforce import SalesforceCrmSource
from .synthetic import SyntheticCrmSource

__all__ = ["SalesforceCrmSource", "SyntheticCrmSource"]
