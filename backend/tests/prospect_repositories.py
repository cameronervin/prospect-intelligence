"""Prospect repositories and fictional account data used only by tests."""

from app.features.prospect_intelligence.contracts.models import (
    Account,
    AccountRelationship,
    OutreachDraft,
)


def outreach_v2(
    *,
    account_name: str = "Acme Foods",
    contact_name: str = "Jordan Lee",
    rep_display_name: str = "Sales representative",
    origin: str = "PHX",
    destination: str = "LAX",
    question: str = "Would you be open to a brief conversation next week to compare network needs?",
) -> OutreachDraft:
    return OutreachDraft(
        subject=f"A freight conversation for {account_name}",
        body=(
            f"Hi {contact_name.split(maxsplit=1)[0]},\n\n"
            f"I'm {rep_display_name}, and I represent an asset-based truckload carrier.\n\n"
            f"{account_name}' distribution footprint and {origin}-to-{destination} freight "
            "activity may align with lanes our team supports.\n\n"
            f"{question}"
        ),
    )


class InMemoryAccountRepository:
    def __init__(self, accounts: tuple[Account, ...] = ()) -> None:
        self._accounts = accounts

    @classmethod
    def seeded(cls) -> "InMemoryAccountRepository":
        return cls(
            (
                Account(
                    id="acme-foods",
                    tenant_id="tenant-demo",
                    name="Acme Foods",
                    relationship=AccountRelationship.PROSPECT,
                    industry="Food distribution",
                    location="Dallas, TX",
                    contact_name="Jordan Lee",
                    contact_role="Director of Transportation",
                ),
                Account(
                    id="northstar-retail",
                    tenant_id="tenant-demo",
                    name="Northstar Retail",
                    relationship=AccountRelationship.CUSTOMER,
                    industry="Retail",
                    location="Atlanta, GA",
                    contact_name="Taylor Brooks",
                    contact_role="Vice President of Logistics",
                ),
            )
        )

    def list_for_actor(
        self,
        tenant_id: str,
        subject: str,
        rep_id: str,
    ) -> tuple[Account, ...]:
        del subject, rep_id
        return tuple(account for account in self._accounts if account.tenant_id == tenant_id)

    def get_for_actor(
        self,
        tenant_id: str,
        subject: str,
        rep_id: str,
        account_id: str,
    ) -> Account | None:
        del subject, rep_id
        return next(
            (
                account
                for account in self._accounts
                if account.tenant_id == tenant_id and account.id == account_id
            ),
            None,
        )
