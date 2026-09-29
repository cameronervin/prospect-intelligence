---
paths:
  - "backend/app/features/**/agents/**"
  - "backend/evaluation/**"
  - "backend/tests/**"
  - "docs/evaluation/**"
---

# Agent and evaluation rules

- Define typed graph state, structured inputs/outputs, explicit tools, and a named human-review boundary.
- Keep graph topology separate from node implementation and business services.
- Make datasets deterministic, synthetic, versioned, and representative of success, boundary, dependency-failure, and adversarial cases.
- Unit tests and CI must not call model providers or LangSmith.
- Record dataset, evaluator, prompt/graph revision, experiment URL, and result interpretation for live experiments.
- Treat traces as sensitive. Minimize captured inputs and outputs and document retention assumptions.
- Never equate passing repository tests with a successful LangSmith experiment or production deployment.
