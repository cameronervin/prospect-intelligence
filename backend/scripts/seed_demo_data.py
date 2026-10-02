"""Idempotently seed the local demo identity and its assigned prospect account."""

from pwdlib import PasswordHash
from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.features.authentication.models import MembershipRecord, TenantRecord, UserRecord
from app.features.prospect_intelligence.models import AccountAssignmentRecord, AccountRecord
from app.platform.config.settings import Settings

_TENANT_ID = "tenant-demo"
_SUBJECT = "usr_alex_morgan"
_REP_ID = "alex-morgan"
_EMAIL = "alex.morgan@example.test"

_ACCOUNTS = (
    {
        "tenant_id": _TENANT_ID,
        "account_id": "sysco-corporation",
        "name": "Sysco Corporation",
        "relationship": "Prospect",
        "industry": "Food distribution",
        "location": "Houston, TX",
        "contact_name": "Jordan Lee",
        "contact_role": "Director of Transportation",
        "fmcsa_usdot_number": "2215799",
    },
)
_RETIRED_ACCOUNT_IDS = ("acme-foods", "northstar-retail")


def demo_password_hash(existing: str | None) -> str:
    """Preserve a valid Argon2id credential without resetting an operator change."""

    passwords = PasswordHash.recommended()
    if (
        existing is not None
        and existing.startswith("$argon2id$")
        and passwords.current_hasher.identify(existing)
    ):
        return existing
    return passwords.hash("prospect-demo")


def seed_demo_data(engine: Engine) -> None:
    """Seed all related demo rows in one transaction without rotating a valid hash."""

    with Session(engine) as session, session.begin():
        existing_hash = session.scalar(
            select(UserRecord.password_hash).where(UserRecord.email == _EMAIL)
        )
        password_hash = demo_password_hash(existing_hash)

        tenant = insert(TenantRecord).values(tenant_id=_TENANT_ID, name="Demo Freight Team")
        session.execute(
            tenant.on_conflict_do_update(
                index_elements=[TenantRecord.tenant_id],
                set_={"name": "Demo Freight Team"},
            )
        )

        user_values = {
            "subject": _SUBJECT,
            "email": _EMAIL,
            "display_name": "Alex Morgan",
            "password_hash": password_hash,
        }
        user = insert(UserRecord).values(**user_values)
        session.execute(
            user.on_conflict_do_update(
                index_elements=[UserRecord.subject],
                set_=user_values,
            )
        )

        membership_values = {
            "subject": _SUBJECT,
            "tenant_id": _TENANT_ID,
            "rep_id": _REP_ID,
            "roles": ["sales_rep"],
        }
        membership = insert(MembershipRecord).values(**membership_values)
        session.execute(
            membership.on_conflict_do_update(
                index_elements=[MembershipRecord.subject],
                set_=membership_values,
            )
        )

        session.execute(
            delete(AccountAssignmentRecord).where(
                AccountAssignmentRecord.tenant_id == _TENANT_ID,
                AccountAssignmentRecord.subject == _SUBJECT,
                AccountAssignmentRecord.rep_id == _REP_ID,
                AccountAssignmentRecord.account_id.in_(_RETIRED_ACCOUNT_IDS),
            )
        )

        for values in _ACCOUNTS:
            account = insert(AccountRecord).values(**values)
            session.execute(
                account.on_conflict_do_update(
                    index_elements=[AccountRecord.tenant_id, AccountRecord.account_id],
                    set_=values,
                )
            )
            assignment_values = {
                "tenant_id": _TENANT_ID,
                "subject": _SUBJECT,
                "rep_id": _REP_ID,
                "account_id": values["account_id"],
            }
            assignment = insert(AccountAssignmentRecord).values(**assignment_values)
            session.execute(
                assignment.on_conflict_do_nothing(
                    index_elements=[
                        AccountAssignmentRecord.tenant_id,
                        AccountAssignmentRecord.subject,
                        AccountAssignmentRecord.rep_id,
                        AccountAssignmentRecord.account_id,
                    ]
                )
            )


def main() -> None:
    settings = Settings(
        demo_auth_enabled=False,
        runtime_jev_guardrails_enabled=False,
        online_quality_enabled=False,
    )
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
        },
    )
    try:
        seed_demo_data(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
