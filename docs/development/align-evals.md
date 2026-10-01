# Aligning Evaluators After Experiments

This document explains how hosted experiment results are used to correct evaluator behavior. The
goal is to separate agent failures from evaluator failures before making a model or prompt decision.

## What the CAM-40 experiments exposed

The original numeric-grounding score was zero for almost every hosted run. Manual review and a
read-only local audit showed that many failures were not unsupported business claims.

The evaluator treated these values as quantities:

- Parts of ISO dates and timestamps, such as `2026-09-29`.
- Markdown list markers, such as `1.` and `2)`.
- Source version labels, such as `FAF5.7.1`.

The evidence projection also omitted valid support:

- Numeric values under `/context/`, including CRM and carrier-network facts.
- Numbers embedded in an evidence item's `claim` string.

This made the score a poor measure of numeric grounding. It was measuring document syntax and an
incomplete evidence projection as well as unsupported quantities.

## Changes made

Numeric grounding now uses these rules:

1. Read numeric evidence from `/context/`, `/research/`, and `/analysis/` JSON artifacts.
2. Accept native numeric values and strings whose complete value is numeric.
3. Extract embedded numbers only from fields named `claim`. Do not scan provenance URLs, source
   versions, record identifiers, or arbitrary text fields for supporting values.
4. Remove complete ISO date and datetime spans before quantitative extraction. Both `T` and space
   separators are supported. Date support belongs to citation and claim review, not this score.
5. Remove alpha-prefixed dotted version labels before numeric extraction. `FAF5.7.1` is a label, but
   a standalone `7.1` remains a quantitative claim.
6. Ignore Markdown ordered-list markers only at the start of a line. Quantities later on the same
   line are still checked.
7. Keep bare years, money, percentages, counts, distances, rates, and modeled values in scope.
8. Fail closed when a required evidence artifact is missing or malformed.

The application-owned scorer and the LangSmith evaluator use the same behavior. Parity tests cover
supported and unsupported claims, date spans, versions, list markers, context values, evidence claim
strings, and malformed evidence.

This behavior change advances the evaluator revision from `freight-evaluators-v2` to
`freight-evaluators-v3`. Online events must carry the exact current revision before semantic
judging. Events already queued with v2 remain durable records, but semantic processing routes them
to annotation as incompatible instead of applying v3 rules to a v2 projection.

## Re-scoring retained experiments

Evaluator corrections do not require another model run. Existing synthetic outputs can be read from
LangSmith and scored locally against regenerated canonical synthetic source artifacts.

The re-score process must:

- Read root outputs only.
- Make no model or Jev calls.
- Create no traces, experiments, or feedback.
- Deduplicate identical feedback records and reject conflicting duplicates.
- Keep original hosted feedback separate from corrected local scores.
- Report missing or empty retained outputs instead of filling them in.

This process changes the interpretation of retained evidence. It does not rewrite the hosted runs or
claim that a partial experiment became complete.

The CAM-40 local re-score still finds mixed residuals. Numeric suffixes in synthetic company names
and `record:<n>` evidence locators are not quantitative claims, while a smaller set of values may be
genuine unsupported quantities. These cases remain diagnostic. They are not converted to passes by
a broad regex exemption. A later change should pass typed entity labels and evidence locators into
the scorer or evaluate structured claims before rendering them as Markdown.

The online scorer reads normalized source artifacts written by specialists. It now extracts embedded
numbers only from `evidence[*].claim`, but a fabricated evidence item could still support its own
number. The specialist artifact contract and quality review reduce this risk; they do not remove it.
Production hardening should project numeric evidence directly from canonical tool results before the
model writes source artifacts.

## How to review evaluator alignment

For each unexpected result:

1. Confirm whether the agent made the claimed mistake.
2. Classify the mismatch as target behavior, evidence projection, evaluator logic, or judge
   calibration.
3. Add a focused failing test using synthetic data.
4. Make the narrowest rule change that fixes the observed class without allowing unsupported
   claims.
5. Run online/offline parity tests and the credential-free evaluation suite.
6. Re-score retained outputs locally when possible.
7. Record changes to formulas, thresholds, evidence scope, or safety boundaries in the business
   logic log.

Do not tune an evaluator only to raise an aggregate score. A change must have a clear semantic rule
and adversarial coverage.

## Work that remains separate

The seven Jev metrics remain evidence only until CAM-41 supplies human labels and adjudication. Their
scores must not replace deterministic gates. The hosted runner also remains strict: it requires all
24 examples, three repetitions, persisted metadata, and complete evaluator feedback for every
variant before it emits a formal promotion result.
