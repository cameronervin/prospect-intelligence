"""PostgreSQL rep-preference repository."""

from sqlalchemy import insert, select

from ...contracts.models import RepPreference
from ...models.records import RepPreferenceRecord
from .store import PostgresProspectStore


class PostgresPreferenceRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(RepPreferenceRecord)
                .where(
                    RepPreferenceRecord.tenant_id == tenant_id,
                    RepPreferenceRecord.rep_id == rep_id,
                )
                .order_by(RepPreferenceRecord.learned_at)
            ).scalars()
            return tuple(
                RepPreference(
                    tenant_id=row.tenant_id,
                    rep_id=row.rep_id,
                    summary=row.summary,
                    learned_at=row.learned_at,
                )
                for row in rows
            )

    def add(self, preference: RepPreference) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(RepPreferenceRecord).values(
                    tenant_id=preference.tenant_id,
                    rep_id=preference.rep_id,
                    summary=preference.summary,
                    learned_at=preference.learned_at,
                )
            )
