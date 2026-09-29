# Evaluation approach

Offline evaluation decides whether a graph revision is ready to ship. Online evaluation detects
quality changes after release, and reviewed online failures become permanent regression examples.

The credential-free harness provides:

- `freight-prospect-v1`: 16 core and 8 edge examples with deterministic reference outputs.
- A separate, generator-backed pool of 8 traffic accounts with no account-ID overlap.
- Pure evaluators for grounding, lane precision, score correctness, verdicts, files,
  trajectories, injection resistance, latency, cost, and tool calls.
- Seven typed Jev questions pinned to `jev-1.13.0`; the live SDK is injected only during an
  approved experiment.
- Three repetitions per example and named comparisons for model routing, prompt revision, and
  interpreter mode.

Release gates are 100% for grounding, analysis correctness, file contract, trajectory safety,
and injection resistance; lane precision@3 at least 0.80; verdict accuracy at least 0.90; and
actionability and tone at least 4/5. Jev calibration uses 40 human labels per question, five
judge repetitions, and option-order permutation. Rework any question below 85% human agreement
or more than five percentage points behind the comparison LLM judge.

Online quality operations live in `features/agent_quality`. That feature owns rule, dashboard,
alert, annotation-queue, traffic-simulation, and regression-candidate workflows. It receives only
sanitized contracts and reaches LangSmith through an injected gateway. Actor identifiers are
hashed, and raw tool/web output is never sent to Jev.

Use [experiment-result-template.md](experiment-result-template.md) for live evidence. Do not
commit traces, credentials, downloaded result payloads, private data, or full model outputs.

## Dataset provenance and interpretation

`freight-prospect-v1` is generated with seed `28029` and compared byte-for-byte with a committed
golden artifact. The same versioned generator owns the offline and traffic populations. Core cases
plant supported lane overlap; edge cases encode missing coverage, entity ambiguity, source conflict,
no fit, prompt injection, a sparse boundary, equipment mismatch, and dependency failure in the
source payload itself rather than only as labels.

The only non-fictional input is a small FAF5.7.1 snapshot of final 2023 regional truck tonnage from
the U.S. Bureau of Transportation Statistics and Federal Highway Administration. Its manifest stores
the official download, DOI, extraction, retrieval date, upstream SHA-256, and derived snapshot
SHA-256. Raw tonnage is never presented as shipper activity. Synthetic loads/week use a seeded
fictional shipper share between 0.25% and 1.0%, 20 tons per load, 52 weeks per year, and half-up
rounding to a whole load. They are always labeled `project-owned synthetic estimate`. We retain
BTS/FHWA attribution and treat broader
commercial redistribution as requiring legal review.
