# Historical implementation sequence

This internal record summarizes how the MVP was assembled. It is retained as project history, not as
current handover guidance or a live ticket tracker.

1. Define shared contracts, deterministic scenarios, and PostgreSQL persistence.
2. Add source adapters and deterministic lane-fit checks.
3. Build the agent runtime, durable APIs, and credential-free evaluators.
4. Add human review, preference memory, the review console, and Desktop Chrome coverage.
5. Add semantic evaluation, hosted experiments, human alignment, and online-quality operations.
6. Add regression intake, handover documentation, and acceptance rehearsal.

The implementation now runs graph revision v4 with prompt revision `outreach-v4`. Current behavior,
evidence, and remaining production work are documented in the
[system architecture](../architecture/system.md), [evaluation guide](../evaluation/README.md), and
[path to production](../production/path-to-production.md).
