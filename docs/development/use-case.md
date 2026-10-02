# Use Case: Freight Prospect Intelligence for Carrier Sales

## Summary

Sales reps at a truckload carrier spend hours researching shippers before outreach, and most
outreach is still generic. This tool gives each rep a short, evidence-backed brief on a
shipper's actual freight activity and how it fits the carrier's network, plus a draft outreach
message the rep reviews before sending. The goal is more qualified conversations, higher win
rates on lanes that make the carrier money, and fewer empty miles.

---

## The business

- **Company type (assumed):** asset-based truckload carrier. It owns trucks and employs drivers.
- **Customers:** shippers (manufacturers, distributors, retailers) that need freight moved
  between facilities.
- **How the carrier makes money:** revenue per loaded mile. Every mile a truck drives empty
  ("deadhead") is cost with no revenue.
- **Core economic problem:** freight flows are unbalanced. A truck that delivers Dallas →
  Atlanta often has no load for the return trip. Filling those return legs ("backhauls") is
  one of the highest-margin opportunities a carrier has, because the truck is making that
  trip anyway.

### Carrier vs. broker

| | Asset-based carrier (default) | Broker (alternate) |
|---|---|---|
| Owns trucks | Yes | No; matches shippers to third-party carriers |
| Earns | Revenue per loaded mile | Margin between shipper rate and carrier cost |
| "Good fit" shipper | Lanes that fill empty return legs or add density to lanes already run | Lanes where the broker has reliable carrier coverage and margin history |
| Pitch | "We run empty on your lane, so we can price it well and reliably" | "We have proven capacity on your lanes" |

Many large carriers run both an asset fleet and a brokerage arm. The MVP targets the carrier
case; broker logic is a later option. Confirm which model the partner company runs before
building.

---

## The problem

### Current workflow
1. Rep picks a shipper to target (existing account for expansion, or a prospect).
2. Rep manually researches the company: website, news, LinkedIn, CRM history.
3. Rep guesses which lanes the shipper runs, usually without real data.
4. Rep sends generic outreach ("we'd love to earn your business").
5. If there's interest, rep asks the shipper which lanes they need covered, then checks
   internally whether those lanes fit the network.

### Pain points
- **Research is slow and shallow.** Hours per account, and it rarely answers the question
  that matters: what freight does this shipper actually move, and where?
- **Outreach is generic.** Shippers get constant carrier outreach. Messages without specific,
  relevant lane information get ignored.
- **Fit is discovered too late.** The carrier only learns whether a shipper's lanes are
  profitable after the conversation starts, which wastes sales time on poor-fit accounts.
- **Network knowledge is siloed.** Operations knows where trucks run empty; sales often
  doesn't use that when choosing whom to call.

---

## The opportunity

Freight intelligence data now exists that shows real truck activity at shipper facilities.
GenLogs, for example, uses roadside sensors to observe truck movements and offers shipper
lane, facility, and regional data through an API. Combined with the carrier's own network
data, a rep can know before the first call:

- Which lanes a shipper runs and roughly how much volume.
- Which of those lanes match the carrier's empty return legs or dense lanes.
- What the opportunity is worth.

That turns outreach from "we'd love to work with you" into "you ship about 40 loads a week
Atlanta → Dallas, and we have trucks heading that direction every day."

---

## The solution

For a selected shipper account, the tool:

1. **Gathers context:** CRM history and current business with the shipper.
2. **Researches freight activity:** shipper lanes, facilities, and volumes from freight
   intelligence data; market lane volumes from public freight data; company news and
   financials from public sources.
3. **Scores network fit:** compares each shipper lane against the carrier's network, focusing
   on backhaul gaps, existing lane density, and equipment match, then sizes the opportunity.
4. **Writes a sales brief:** top-fit lanes, supporting evidence, sized opportunity, and a
   recommended next step (expand existing lanes, pitch new lanes, not a fit, or needs more data).
5. **Drafts outreach:** a message tailored to the shipper and the rep's style.
6. **Waits for the rep:** nothing is sent and the CRM is not updated until the rep approves,
   edits, or rejects.

### Users and stakeholders

| Role | Interest |
|---|---|
| Sales rep (primary user) | Faster research, better conversations, higher close rate |
| Sales leadership (buyer) | Pipeline quality, rep productivity, revenue on target lanes |
| Network / operations planning | Freight that improves truck utilization and reduces empty miles |
| Pricing | Opportunities on lanes where the carrier can price competitively |
| Legal / compliance | Third-party data used within license terms; nothing sent without human review |

---

## Data sources

| Source | What it provides | MVP approach |
|---|---|---|
| Freight intelligence (GenLogs) | Shipper lanes, facilities, volumes | Simulated, following the vendor's published data format (commercial license required for real data) |
| Public freight flow data (FHWA FAF5) | Market-level freight volumes between regions | Real |
| FMCSA | Carrier and safety data | Real |
| SEC EDGAR | Financials and facility or expansion mentions for public shippers | Real |
| Web search | Company news, expansion signals | Real |
| CRM | Account history, contacts, current business | Simulated |
| Carrier network data | Lanes run, weekly loads, where trucks run empty | Simulated |

---

## Value and ROI framing

Illustrative model for the stakeholder conversation; all inputs are assumptions to replace
with the partner company's real numbers.

- **Rep time saved:** research hours per account × accounts per rep per week × loaded rep cost.
- **Better targeting:** share of outreach aimed at high-fit shippers, before vs. after.
- **Revenue:** matched loads per week × average rate per load × 52 weeks, for accounts won.
- **Margin uplift:** backhaul loads replace empty miles, so each one improves utilization
  beyond its revenue.

The strongest pitch is the last point: a won backhaul lane is worth more to a carrier than
its rate alone, because it converts cost (empty miles) into revenue.

---

## How success is measured

**Before rollout (quality gates):**
- Every figure in the brief traces to a source; no invented numbers.
- The tool correctly identifies the best-fit lanes and correctly flags poor-fit shippers.
- Reps rate the briefs as actionable.

**In production (business outcomes):**
- Rep approval rate of drafts, and how much reps edit them.
- Research time per account.
- Outreach reply rate and meetings booked, vs. baseline.
- Opportunities created and won on high-fit lanes.
- Empty-mile reduction on lanes where business was won (longer-term).

---

## Risks and constraints

| Risk | Mitigation |
|---|---|
| Wrong or invented numbers damage credibility with a prospect | Every figure must trace to a source; checked automatically; rep reviews before sending |
| Third-party data license limits what can be shared with prospects | Rules on what appears in outreach; legal review of license terms |
| Freight data cost (commercial licenses are expensive) | Prove value on simulated plus public data first; cache and limit paid calls |
| Reps over-trust the tool | Rep approval required for every send and CRM update; evidence shown with each claim |
| Data access and privacy across sales teams | Reps see only their own accounts and territory |
| Shipper's lanes change over time | Briefs are dated; data refreshed on each run |

---

## MVP scope and next decision

**In scope:** end-to-end brief and draft for a set of shipper accounts using simulated
freight, CRM, and network data plus real public sources; rep approval step; quality
measurement before and after deployment.

**Out of scope:** real freight intelligence license, real email sending, real CRM writes,
broker mode.

**Decision for the stakeholder:** whether to fund phase 2, which would add a real freight data
license, CRM integration, and a pilot with a small group of reps measured against a control
group on reply rate, meetings booked, and revenue on target lanes.
