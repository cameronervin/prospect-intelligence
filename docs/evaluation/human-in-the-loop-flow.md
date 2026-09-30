# Human-in-the-loop review flow

Human in the loop (HITL) means the agent cannot finish an outreach action by itself. It prepares a
safe draft, pauses, and waits for a sales rep to approve, edit, or reject it. This keeps the rep in
control of customer-facing communication while still producing measurable feedback for later runs.

The MVP does not send email or write to a CRM. An approved or edited draft creates a simulated send
receipt so the workflow and recovery behavior can be evaluated safely.

## Flow

```text
agent drafts outreach and passes guardrails
                  |
                  v
root requests send_outreach -> LangGraph saves a durable interrupt
                  |
                  v
rep approves, edits, or rejects through the API
                  |
                  v
scope, review token, and edited content are validated
                  |
                  v
the same checkpoint resumes and the graph finalizes
                  |
                  v
PostgreSQL atomically commits the decision and related records
                  |
                  v
sanitized quality event waits in the outbox for delivery
```

## Decision results

| Decision | Product result | Learning and evaluation result |
| --- | --- | --- |
| Approve | Complete the run and record the original draft in one simulated receipt. | Record approval and edit distance `0`. Do not change preference memory. |
| Edit | Validate the complete revised subject and body, complete the run, and record that version once. | Record normalized edit distance and replace the current tenant/rep style profile. |
| Reject | Mark the run rejected and create no receipt. | Record rejection with no edit distance. Do not change preference memory. |

Edited copy must match the same exact public-safe invitation templates used for generated drafts.
Validation happens before checkpoint resume and again before persistence. An unsafe or incomplete
first-time edit does not resume the graph and does not create a receipt, preference, or quality
event.

## Main methods and responsibilities

| Method or component | Responsibility |
| --- | --- |
| Graph `finalize` node | Calls LangGraph `interrupt()` with the review payload and stores the resumed decision in graph state. |
| `ProspectAgentReviewHandler` | Checks the run token, serializes review attempts per process, validates edits, inspects the checkpoint, and resumes the graph. |
| `CompiledProspectAgentRuntime.resume_review()` | Sends the approve, edit, or reject payload back to the same thread with `Command(resume=...)`. |
| `prepare_review_outcome()` | Applies the decision, validates the selected outreach, builds the simulated receipt, calculates feedback, and derives a bounded preference when needed. |
| `PostgresWorkflowRepository.commit_review()` | Commits the review record, run state, optional receipt, optional preference, and quality event in one database transaction. |
| `build_quality_event()` and `QualityEventDispatcher` | Create the sanitized event, publish it asynchronously, and mark it delivered only after sink success. |

## Durability and duplicate requests

The LangGraph checkpoint and product transaction are separate durable boundaries. The graph resumes
first. The product decision then commits to PostgreSQL. If that commit fails after graph finalization,
a retry verifies that the completed checkpoint contains the same decision and retries the database
commit without rerunning the agent.

Each review token belongs to one run. The first valid decision becomes canonical:

- Repeating the same action returns the original result.
- A repeated edit cannot replace the original accepted edit with different copy.
- A different action for the same token is rejected.
- An invalid token or a decision for another run changes nothing.
- Concurrent requests produce one review record, one receipt when applicable, one review event, and
  at most one current preference profile.

## Preference memory

Only an accepted edit updates memory. The stored profile contains three neutral traits: tone, body
word count, and generic or route-specific invitation format. It never stores draft text, account
names, route codes, or customer facts.

There is one current profile per tenant and rep. The newest `learned_at` value wins if reviews commit
out of order. A later run loads that profile and materializes it in the tenant/rep StoreBackend
namespace. Agents without permission to read rep memory cannot access it.

## Quality and privacy signals

Review feedback uses the canonical text `Subject: …\n\n<body>`. Edit distance is character-level
Levenshtein distance divided by the longer canonical text length. Approval records `0`; edit records
the calculated value; rejection records no distance.

The durable `review_completed` event contains only the approved quality-event fields. Tenant and rep
identifiers are SHA-256 hashes; the established event contract keeps the raw account ID. Draft text,
prompts, customer facts, provider payloads, and provider errors are excluded. Online monitoring can
use approve, edit, and reject rates, edit distance, and reject spikes without reading the draft.

Outbox delivery is at least once. Event IDs are deterministic so downstream systems can deduplicate.
A sink failure or 10-second timeout leaves the event pending, records only a safe error code, and
does not fail or change the user's run.

## Current boundaries

- Repository tests prove workflow, checkpoint, persistence, guardrail, concurrency, and dispatcher
  behavior. They are not evidence of a live LangSmith experiment.
- Concrete LangSmith quality-event delivery is deferred to CAM-42.
- Real email, CRM writeback, customer-specific memory, and production retention controls are outside
  this MVP.
