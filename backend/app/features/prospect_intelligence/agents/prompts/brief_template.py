"""The internal sales-brief template shared by the orchestrator and the quality reviewer."""

BRIEF_TEMPLATE = """
# Brief template

/output/brief.md is internal to the sales team. It must be valid Markdown with these sections, in
this order and with these exact headings:

```markdown
# <Account name> — Freight prospect brief

## Summary
Two to four sentences: who the shipper is, what we found, and whether it is worth the rep's time.

## Verdict and recommended next step
The lane_fit_v1 verdict exactly as written in /analysis/lane_fit.json (fit, no_fit, or
needs_more_data) and one recommended next step:
- fit: open a conversation about the top lane.
- no_fit: deprioritize this account.
- needs_more_data: verify the shipper's lanes before any outreach.

## Top lanes
A table with one row per top lane from /analysis/lane_fit.json, in its order, with columns: Lane,
Shipper loads/week, Matched loads/week, Fit score, Modeled annual revenue, Modeled deadhead miles
avoided. Write "No eligible lanes." when there are none.

## Evidence and sources
One bullet per key fact: the fact, then its source, mode (live, fixture, or snapshot), retrieval
date, and opaque `[ev_...]` citation id copied from the evidence record.

## Risks and data gaps
Degraded or unavailable sources, assumptions behind modeled figures, and anything unverified.

## Discovery questions
Three to five questions the rep should ask the shipper to confirm fit.
```
""".strip()
