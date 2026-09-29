"""PostgreSQL rep-preference repository."""

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ...contracts.models import RepPreference
from ...models.records import RepPreferenceRecord
from .store import PostgresProspectStore


class PostgresPreferenceRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(RepPreferenceRecord)
                .where(
                    RepPreferenceRecord.tenant_id == tenant_id,
                    RepPreferenceRecord.rep_id == rep_id,
                )
                .order_by(RepPreferenceRecord.learned_at)
            )
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
        with Session(self._engine) as session, session.begin():
            session.execute(
                insert(RepPreferenceRecord).values(
                    tenant_id=preference.tenant_id,
                    rep_id=preference.rep_id,
                    summary=preference.summary,
                    learned_at=preference.learned_at,
                )
            )
