"""Atomic PostgreSQL persistence for reviewed regression intake."""

from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.features.agent_quality.domain.regression import (
    AuditAction,
    CandidateStatus,
    DuplicateRegressionCandidateError,
    PromotedRegressionExample,
    RegressionAuditEntry,
    RegressionCandidate,
    ReviewDecision,
)
from app.features.agent_quality.models import (
    RegressionAuditRecord,
    RegressionCandidateRecord,
    RegressionExampleRecord,
)
from app.features.agent_quality.repositories._postgres_mappers import (
    audit_from_record,
    candidate_from_record,
    candidate_values,
    example_from_record,
)


class PostgresRegressionRepository:
    """Persist state transitions and their audit event in one transaction."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def create(self, candidate: RegressionCandidate) -> RegressionCandidate:
        values = candidate_values(candidate)
        statement = (
            insert(RegressionCandidateRecord)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(RegressionCandidateRecord.candidate_id)
        )
        with Session(self._engine) as session, session.begin():
            inserted_id = session.scalar(statement)
            if inserted_id is not None:
                session.add(
                    RegressionAuditRecord(
                        candidate_id=candidate.candidate_id,
                        action=AuditAction.CREATED.value,
                        actor=candidate.source_kind.value,
                        occurred_at=candidate.created_at,
                        details={
                            "signature": candidate.signature,
                            "source_kind": candidate.source_kind.value,
                        },
                    )
                )
                return candidate

            by_id = session.get(RegressionCandidateRecord, candidate.candidate_id)
            if by_id is not None:
                persisted = candidate_from_record(by_id)
                if persisted == candidate:
                    return persisted
                raise ValueError("candidate id already exists with a different payload")

            by_signature = session.scalar(
                select(RegressionCandidateRecord).where(
                    RegressionCandidateRecord.signature == candidate.signature
                )
            )
            if by_signature is None:  # pragma: no cover - defensive against external deletion
                raise RuntimeError("regression candidate conflict could not be resolved")
            raise DuplicateRegressionCandidateError(by_signature.candidate_id)

    async def get(self, candidate_id: str) -> RegressionCandidate | None:
        with Session(self._engine) as session:
            record = session.get(RegressionCandidateRecord, candidate_id)
            return candidate_from_record(record) if record is not None else None

    async def get_by_signature(self, signature: str) -> RegressionCandidate | None:
        with Session(self._engine) as session:
            record = session.scalar(
                select(RegressionCandidateRecord).where(
                    RegressionCandidateRecord.signature == signature
                )
            )
            return candidate_from_record(record) if record is not None else None

    async def review(
        self,
        candidate_id: str,
        *,
        decision: ReviewDecision,
        reviewer: str,
        reason: str,
        reviewed_at: datetime,
    ) -> RegressionCandidate:
        desired_status = (
            CandidateStatus.ACCEPTED
            if decision is ReviewDecision.ACCEPT
            else CandidateStatus.REJECTED
        )
        with Session(self._engine) as session, session.begin():
            record = _locked_candidate(session, candidate_id)
            candidate = candidate_from_record(record)
            if candidate.status is not CandidateStatus.PENDING:
                accepted_after_promotion = (
                    desired_status is CandidateStatus.ACCEPTED
                    and candidate.status is CandidateStatus.PROMOTED
                )
                if (
                    (candidate.status is desired_status or accepted_after_promotion)
                    and candidate.reviewer == reviewer
                    and candidate.review_reason == reason
                ):
                    return candidate
                raise ValueError("candidate has a conflicting review")

            reviewed = candidate.review(
                decision=decision,
                reviewer=reviewer,
                reason=reason,
                reviewed_at=reviewed_at,
            )
            record.status = reviewed.status.value
            record.reviewer = reviewed.reviewer
            record.review_reason = reviewed.review_reason
            record.reviewed_at = reviewed.reviewed_at
            action = (
                AuditAction.ACCEPTED if decision is ReviewDecision.ACCEPT else AuditAction.REJECTED
            )
            session.add(
                RegressionAuditRecord(
                    candidate_id=candidate_id,
                    action=action.value,
                    actor=reviewer,
                    occurred_at=reviewed_at,
                    details={"reason": reason},
                )
            )
            return reviewed

    async def promote(
        self,
        candidate_id: str,
        *,
        example: PromotedRegressionExample,
        promoted_at: datetime,
    ) -> PromotedRegressionExample:
        if example.candidate_id != candidate_id:
            raise ValueError("promotion candidate does not match requested candidate")
        if example.promoted_at != promoted_at:
            raise ValueError("promotion timestamp does not match promoted example")

        with Session(self._engine) as session, session.begin():
            record = _locked_candidate(session, candidate_id)
            candidate = candidate_from_record(record)
            if candidate.status is CandidateStatus.PROMOTED:
                persisted_record = session.scalar(
                    select(RegressionExampleRecord).where(
                        RegressionExampleRecord.candidate_id == candidate_id
                    )
                )
                if persisted_record is None:  # pragma: no cover - database invariant
                    raise RuntimeError("promoted candidate has no regression example")
                persisted = example_from_record(persisted_record)
                submitted = PromotedRegressionExample.from_candidate(
                    candidate,
                    promoted_at=promoted_at,
                )
                persisted_at = candidate.promoted_at
                if persisted_at is None:  # pragma: no cover - database invariant
                    raise RuntimeError("promoted candidate has no promotion timestamp")
                expected_persisted = PromotedRegressionExample.from_candidate(
                    candidate,
                    promoted_at=persisted_at,
                )
                if example == submitted and persisted == expected_persisted:
                    return persisted
                raise ValueError("candidate has a conflicting promotion")
            if candidate.status is not CandidateStatus.ACCEPTED:
                raise ValueError("candidate must be accepted before promotion")
            expected = PromotedRegressionExample.from_candidate(
                candidate,
                promoted_at=promoted_at,
            )
            if example != expected:
                raise ValueError("promoted example does not match accepted candidate")

            promoted_candidate = candidate.promoted(promoted_at=promoted_at)
            session.add(
                RegressionExampleRecord(
                    example_id=example.example_id,
                    candidate_id=example.candidate_id,
                    version=example.version,
                    split=example.split,
                    signature=example.signature,
                    inputs=dict(example.inputs),
                    reference_outputs=dict(example.reference_outputs),
                    example_metadata=dict(example.metadata),
                    checksum=example.checksum,
                    promoted_at=example.promoted_at,
                )
            )
            record.status = promoted_candidate.status.value
            record.promoted_at = promoted_candidate.promoted_at
            session.add(
                RegressionAuditRecord(
                    candidate_id=candidate_id,
                    action=AuditAction.PROMOTED.value,
                    actor=candidate.reviewer or "system",
                    occurred_at=promoted_at,
                    details={
                        "checksum": example.checksum,
                        "example_id": example.example_id,
                    },
                )
            )
            return example

    async def list_audit(self, candidate_id: str) -> tuple[RegressionAuditEntry, ...]:
        with Session(self._engine) as session:
            records = session.scalars(
                select(RegressionAuditRecord)
                .where(RegressionAuditRecord.candidate_id == candidate_id)
                .order_by(RegressionAuditRecord.id)
            ).all()
            return tuple(audit_from_record(record) for record in records)

    async def list_promoted(self) -> tuple[PromotedRegressionExample, ...]:
        with Session(self._engine) as session:
            records = session.scalars(
                select(RegressionExampleRecord).order_by(RegressionExampleRecord.example_id)
            ).all()
            return tuple(example_from_record(record) for record in records)


def _locked_candidate(session: Session, candidate_id: str) -> RegressionCandidateRecord:
    record = session.scalar(
        select(RegressionCandidateRecord)
        .where(RegressionCandidateRecord.candidate_id == candidate_id)
        .with_for_update()
    )
    if record is None:
        raise LookupError(f"regression candidate not found: {candidate_id}")
    return record
