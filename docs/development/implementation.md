# Implementation order

Linear is the source of truth for ticket scope, status, and dependencies. This file only shows what to pick up next. Tickets on the same line can run in parallel once all earlier blockers are complete.

1. **Now:** CAM-27 — finalize the shared contracts.
2. **After CAM-27:** CAM-28 — deterministic data; CAM-29 — persistence.
3. **After CAM-28:** CAM-30 — source adapters; CAM-31 — lane-fit verification.
4. **After CAM-29, CAM-30, and CAM-31:** CAM-32 — working agent topology.
5. **After CAM-32:** CAM-33 — durable APIs; CAM-38 — offline evaluators.
6. **After CAM-33:** CAM-34 — HITL and preference learning; CAM-35 — first UI slice.
7. **After CAM-34 and CAM-35:** CAM-36 — review UI. **After CAM-38:** CAM-39 — Jev evaluators.
8. **After CAM-36:** CAM-37 — browser tests. **After CAM-34 and CAM-39:** CAM-42 — online-quality feature.
9. **After CAM-42:** CAM-43 — online rules and simulator. **After CAM-37, CAM-38, and CAM-39:** CAM-40 — LangSmith experiments.
10. **After CAM-40:** CAM-41 — human calibration, owned by Cameron.
11. **After CAM-40, CAM-41, and CAM-43:** CAM-44 — reviewed regression intake.
12. **After CAM-37 and CAM-44:** CAM-45 — final documentation and demo material.
13. **After CAM-45:** CAM-46 — final acceptance and rehearsal.
14. **Optional after CAM-46:** CAM-47 and CAM-48 — stretch work.

Before starting a ticket, confirm its blockers and current state in Linear. A `Todo` ticket may already contain scaffolding; read its handoff notes and replace placeholders required by its acceptance criteria.
