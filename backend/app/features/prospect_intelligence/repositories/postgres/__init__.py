"""PostgreSQL repository adapters for prospect intelligence."""

from .accounts import PostgresAccountRepository
from .jobs import PostgresJobRepository
from .preferences import PostgresPreferenceRepository
from .quality_events import PostgresQualityEventOutbox
from .receipts import PostgresSendReceiptRepository
from .runs import PostgresRunRepository
from .store import PostgresProspectStore
from .workflows import PostgresWorkflowRepository

__all__ = [
    "PostgresAccountRepository",
    "PostgresJobRepository",
    "PostgresPreferenceRepository",
    "PostgresProspectStore",
    "PostgresQualityEventOutbox",
    "PostgresRunRepository",
    "PostgresSendReceiptRepository",
    "PostgresWorkflowRepository",
]
