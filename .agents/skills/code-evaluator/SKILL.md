---
name: code-evaluator
description: Evaluate a change against requirements, architecture, tests, security, operations, and evidence without modifying it.
---

# Code evaluator

Use for reviews and release gates. Report evidence; do not edit unless a separate request authorizes fixes.

1. Map changed behavior to the assignment, current feature spec, and acceptance criteria.
2. Trace untrusted inputs through schemas, services or agent nodes, repositories/integrations, logs, and user-visible output.
3. Inspect tests before running them. Confirm they can fail for the target defect and cover boundaries and dependency failure.
4. Run focused tests, then `make verify`, `make secret-scan`, and delivery checks when relevant.
5. Review dependency direction, human-review gates, data isolation, idempotency, bounded I/O, trace privacy, container health, and rollback.
6. Rank findings by severity and confidence with file/line evidence and a concrete reproduction or missing-test description.

Lead with findings. Then list questions, assumptions, validation performed, and residual live-evidence gaps.

