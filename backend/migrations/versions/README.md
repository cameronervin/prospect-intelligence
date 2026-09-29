# Migrations

`20260929_0001_prospect_intelligence.py` owns the first product tables for accounts, durable runs,
worker claims, reviews, simulated-send receipts, and rep preferences. Its downgrade deletes those
tables and their data.

LangGraph checkpoint and store tables are initialized through the installed package's idempotent
`setup()` migrations. They are deliberately outside Alembic and are not removed by the product
downgrade.
