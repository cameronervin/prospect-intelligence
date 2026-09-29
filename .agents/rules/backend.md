---
paths:
  - "backend/**"
---

# Backend rules

- Write a failing unit, contract, or architecture test before behavior changes.
- Keep application assembly in `bootstrap`; shared technical capabilities in `platform`; universal business types in `shared_kernel`; business behavior in `features`.
- Preserve `api -> services/agents -> contracts/domain <- repositories/integrations`.
- Keep FastAPI in `api`, Pydantic edge contracts in `schemas`, SQLAlchemy records in `models`, and concrete wiring in `bootstrap`.
- Inject repositories, external clients, model access, checkpointers, and clocks. Do not create them inside routes, services, nodes, or tools.
- Export cross-feature behavior only through `public.py` or `contracts/`.
- Keep strict Pyright and Ruff clean. Use async only at real I/O boundaries.
- Bound external I/O, classify retryable failures, and make side effects idempotent before retrying.
- Use structured logging and never log prompts, credentials, private data, or full model outputs by default.

