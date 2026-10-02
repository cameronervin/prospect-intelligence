# Migrations

`20260929_0001_prospect_intelligence.py` owns the first product tables for accounts, durable runs,
worker claims, reviews, simulated-send receipts, and rep preferences. Its downgrade deletes those
tables and their data.

`20260929_0002_quality_event_outbox.py` keeps only the newest preference for each tenant/rep scope,
enforces one current profile per scope, and adds the sanitized quality-event delivery outbox. Its
downgrade removes the outbox and preference uniqueness constraint; deleted duplicate preferences
cannot be restored.

`20261001_0004_account_ownership.py` moves tenant, rep, and role authority from user profiles into a
single membership per user, adds fictional account contacts, and requires explicit actor-scoped
account assignments. Existing users are backfilled into memberships; existing accounts are retained
without assignments until the explicit demo seed or another provisioning workflow assigns them.

LangGraph checkpoint and store tables are initialized through the installed package's idempotent
`setup()` migrations. They are deliberately outside Alembic and are not removed by the product
downgrade.
