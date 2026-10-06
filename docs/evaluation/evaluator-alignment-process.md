# Evaluator alignment to human preference

CAM-41/CAM-50 assess whether the seven `semantic-v1` questions reproduce a human reviewer's
judgment closely enough to remain useful. The process starts with reference labels, not judge outputs:
one designated reviewer examines sanitized cases blind, freezes those labels, and only then are Jev and GPT-5.6 Sol
measured against them. This is a single-reviewer, two-pass adjudication workflow, not inter-rater
validation.

This document defines the process and the evidence required to explain it. On 2026-10-01, live
preparation was read back as 280 roots before the MVP scope was reduced. The live workflow
reconciled the seven primary queues to 10 selected items each. The complete primary pass, 13 required
second-pass adjudications, and the 70-example `cam-41-labels-v1` dataset were read back successfully.
The separately authorized alignment phase is now published and read back in LangSmith as 210 attempt
roots plus 210 human-agreement feedback records. The untouched holdout has not run.
On 2026-10-01 the product owner explicitly closed CAM-41/CAM-50 without that optional live phase:
the take-home objective is to demonstrate a human-first alignment lifecycle, not claim independent
holdout validation or production readiness. The holdout path remains implemented for future use.

The first authorized alignment execution on 2026-10-01 exhausted its 630-request envelope across
three matrices before a LangSmith `limit <= 100` run-query constraint was isolated. No alignment
trace project or report was produced, so those calls are cost evidence only—not evaluator evidence.
Bounded trace/feedback queries now have regression coverage; another alignment run requires fresh
authorization. A later authorized matrix successfully created project
`cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed`. Its 154 valid and 56 unavailable attempts
exposed a score-contract defect confined to `actionability` and `tone_fit`: the shared score
primitive returns a probability-weighted score, while the application adapter incorrectly required
an integer rubric position. The approved bounded revision maps the returned probability distribution
onto canonical 1–5 values under `shared-question-payload-v2-weighted-scores`. A targeted 60-attempt
rerun plus 17 unavailable-only Jev retries now provide complete ordered-score diagnostic coverage.
One bounded prompt experiment, `shared-question-payload-v3-score-anchors`, then made the canonical
score anchors and adjacent-score uncertainty explicit. Its 60/60 valid attempts failed the
predeclared acceptance rule because `tone_fit` within-one agreement regressed and Jev acquired
repeat/order instability on `actionability`; v3 was rejected and v2 remains frozen. A provider-free
composite manifest now references the original categorical evidence and accepted v2 score evidence
as 210/210 read-back-verified alignment attempts. This remains alignment evidence, not a holdout
result or pass.

## 1. Build the reference set

The versioned label set is `cam-41-labels-v1`. For each of the seven `semantic-v1` questions, the
preparation command deterministically selects exactly 10 applicable cases with seed `28029`.
Selection is deduplicated by metric and canonical projected-state hash, and covers:

- core behavior;
- edge behavior;
- intended positive, negative, choice, or score classes as applicable;
- ambiguous and adversarial states; and
- synthetic states shaped to exercise the compatible CAM-40 experiment variants.

The repository does not retain CAM-40 row state, so v1 is intentionally all synthetic; variant tags
mean compatibility with those experiment conditions, not provenance from a historical trace.
Synthetic provenance is explicit in case metadata and never changes the expected total.
Each question is then split into five alignment cases and five untouched holdout cases. A projected-state
hash may appear in only one split for that question.

The local projection is authoritative. Before publication, preparation regenerates every projection
from its versioned source and rejects missing values, duplicate or conflicting case IDs/hashes,
non-finite values, version mismatches, hash mismatches, oversized state, unknown fields, or incomplete
question coverage. Annotation queues contain only the bounded projected state, rubric criteria, and
case metadata. They never expose Jev or GPT-5.6 Sol answers, probabilities, rationales, or scores.

## 2. Create blind reference labels

One designated reviewer completes the MVP pass. The primary pass records all of the following for every case:

- the canonical label defined by the question contract;
- confidence;
- a concise rationale;
- an explicit ambiguity flag; and
- reviewer and review-time metadata.

After all 70 primary labels are complete, their values, timestamps, review method, reviewer name,
and stable reviewer ID are committed to a global SHA-256 freeze record. Direct UI annotations use
LangSmith's human/app source; manually reviewed judgments transported through the SDK retain its
native `api` source and must declare `review_method=manual_rubric_review`.
A case enters a separate
second-pass queue when the primary label is low-confidence or explicitly ambiguous. The second pass
records an adjudicated label and rationale without revealing either automated judge's output. A
label set cannot be approved if any label, rationale, confidence, reviewer/date metadata, required
adjudication, question, or split is missing; if labels conflict; or if its projection no longer
matches the source-controlled hash and versions.

The approved set is described as “single-reviewer, two-pass adjudicated.” It must not be presented
as consensus, inter-rater reliability, or proof of stakeholder-wide preference.

Each queue isolates one judgment so its labels and rubric stay unambiguous:

| Queue key | Reviewer judgment |
| --- | --- |
| `claim_supported` | Whether cited support entails the qualitative claim. |
| `internal_data_leak` | Whether customer-facing text exposes internal-only information. |
| `draft_matches_brief` | Whether outreach preserves the brief's recommendation and next step. |
| `next_step` | Which supported commercial action the brief recommends. |
| `entity_resolution_ok` | Whether the resolved profile matches the intended company. |
| `actionability` | A 1–5 score for how usable the brief is to a sales representative. |
| `tone_fit` | A 1–5 score for adherence to the representative's preferences. |

## 3. Measure judges without tuning on holdout

Calibration runs Jev `jev-1.13.0` and GPT-5.6 Sol three times on every approved case. Both choice and
ordered 1–5 questions use deterministic option permutations; answers are mapped back to their
canonical labels before analysis. Provider failure, invalid output, an unknown answer, or a missing
attempt remains invalid and reduces coverage. One judge never substitutes for the other.

Use the five alignment cases per question to diagnose projection or rubric problems. If the rubric is
changed, version and freeze it before running the five holdout cases. Holdout labels must not be used
to revise the rubric and then re-reported as untouched evidence.

Alignment does not fine-tune either provider model. A disagreement may justify a source-controlled
change to the evaluator prompt, rubric wording, bounded projection, or question boundary. That
revision is frozen before holdout; the resulting decision is `retain`, `revise`, `split`, or
`replace`, while semantic runtime gates remain unchanged.

The v2 change corrected the answer contract: it interprets the shared primitive's legitimate
probability-weighted output without changing rubric wording. The later v3 experiment was the only
substantive prompt change: it labeled the existing 1–5 anchors explicitly and instructed the judge
to choose the closest anchor without inventing unstated requirements. It was evaluated once and
rejected under the frozen comparison rule rather than iterated until the alignment data improved.

For each question and judge, report:

- **Valid-attempt coverage:** valid attempts divided by `3 × case count`. This full denominator is
  never reduced because a provider failed.
- **Exact human agreement:** valid predictions equal to the final human label divided by valid
  attempts, with the full confusion counts alongside it. A probability-weighted ordered score is
  mapped to its nearest canonical 1–5 label (half points round upward) for this categorical view.
- **Balanced accuracy:** the mean recall across required human-label classes for binary and
  categorical questions. If a required class has no human support, report `class_imbalance`; do not
  publish a balanced-accuracy value.
- **Mean absolute error:** for ordered scores, `mean(abs(weighted judge score - human score))` over
  valid attempts; unlike exact agreement, this retains the continuous weighted value.
- **Within-one agreement:** for ordered scores, the share of valid attempts no more than one point
  from the human score.
- **Run-to-run disagreement:** for each case, `1 - (modal valid answer count / valid answer count)`,
  then the mean across cases with a valid answer.
- **Option-order sensitivity:** attempts 1 and 2 repeat the canonical order. A case is eligible only
  when that repeated baseline is stable and at least one valid alternate permutation exists; the
  metric is the proportion of eligible cases where an alternate order changes the canonical answer.
  Report it as observed permutation-associated variation, not causal proof: alternate orders have
  one sample each. Publish alternate-order observed/expected coverage beside the metric.
- **Operational evidence:** the sum of reported judge costs and observed latency, plus cost-telemetry
  coverage and an unavailable count. Missing cost is not interpreted as a real zero.
- **Comparison delta:** Jev exact agreement minus GPT-5.6 Sol exact agreement for the same question
  and split.

Agreement uses valid attempts. A question cannot receive `retain`—or any pass-like conclusion—unless
coverage is 100% over the complete three-run denominator.

## 4. Interpret a future holdout

If the untouched holdout is run, each question can receive one recommendation:

- `retain`: holdout exact agreement is at least 85%, attempt coverage is 100%, and Jev is no more
  than five percentage points behind GPT-5.6 Sol;
- `revise`: a bounded rubric or projection ambiguity is correctable;
- `split`: the question combines judgments that should be evaluated separately; or
- `replace`: after bounded revision, the comparison judge remains materially better.

These are planned interpretation criteria, not promotion thresholds. The holdout did not run, so
CAM-41/CAM-50 produced no formal retain/revise/split/replace recommendations. They do not activate a
semantic gate or change runtime routing. A future business decision to gate on a semantic score
requires a separate logged policy change and release evidence.

## 5. Keep evidence classes separate

The credential-free self-test uses synthetic fixtures and fake judges, makes no network calls, and
is repository evidence only. Preparing queues or running real judges is live evidence and requires
an explicit `--live` path. The full plan contains 420 logical attempts
(`7 questions × 10 cases × 3 repetitions × 2 judges`), staged as 210 alignment and 210 holdout
attempts. Before either phase, the CLI prints that phase's logical attempts, a 3× provider-request
retry ceiling, provider estimates based on pinned price cards and disclosed token assumptions, and
LangSmith trace estimates, then requires explicit live authorization. LangSmith automatically
upgrades traces placed in annotation queues or given feedback to extended retention. At the
workspace rate observed on 2026-10-01 (`$0.0075/trace`), a clean queue preparation is at most `$0.53`
for 70 roots and the traced 420-attempt calibration is `$3.15` in LangSmith trace charges,
before provider charges and subject to the workspace's included usage. The CLI reports these
components separately; a local-only diagnostic has no LangSmith trace estimate and cannot count as
completed evidence.

The successful alignment phase added an estimated `$0.95` in provider usage and `$1.58` for 210
extended traces. Together with the earlier `$2.10` labeling roots and approximately `$2.85` in
provider calls from the failed publication attempts, estimated alignment-related spend to date is
about `$7.48`. The 60-attempt score revision and 17-attempt unavailable-only retry added an estimated
`$0.85`, bringing estimated alignment-related spend to about `$8.33`. The v3 experiment added
`$0.104633` in provider usage, approximately `$0.45` for its 60 traces, and `$0.015` for the
initial and hardened composite manifests, bringing estimated alignment-related spend to about
`$8.90`. The workspace
accepted all alignment writes, so no configured spend limit was hit.
The untouched holdout would require a new preflight and authorization; its current estimate is
another `$2.53`, with a retry-envelope ceiling near `$4.43`.

Run the workflow from `backend/`:

```sh
uv run python -m evaluation.experiments.alignment self-test
uv run python -m evaluation.experiments.alignment prepare-labels --live
uv run python -m evaluation.experiments.alignment prepare-adjudication --live
uv run python -m evaluation.experiments.alignment calibrate --live \
  --phase alignment --label-set cam-41-labels-v1 --authorize-420-calls
uv run python -m evaluation.experiments.alignment calibrate --live \
  --phase alignment --score-revision-only --label-set cam-41-labels-v1 \
  --authorize-60-calls
uv run python -m evaluation.experiments.alignment publish-composite --live \
  --authorize-1-manifest \
  --categorical-project cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed \
  --score-project cam-41-alignment-cam-41-labels-v1-9def2f19d5593cf7 \
  --score-project cam-41-alignment-cam-41-labels-v1-4a7eedede417b378
uv run python -m evaluation.experiments.alignment calibrate --live \
  --phase holdout --label-set cam-41-labels-v1 \
  --confirm-rubric-frozen --authorize-420-calls \
  --composite-project cam-41-alignment-composite-cam-41-labels-v1-039273d2fe8e3143
uv run python -m evaluation.experiments.alignment calibrate --live --local-only \
  --phase alignment --label-set cam-41-labels-v1 --authorize-420-calls \
  --untraced-reason "documented exception"
```

The live paths use environment credentials; never put their values on the command line. The
calibration preview and authorization step happen before provider calls. `prepare-labels` publishes
the projected cases and primary queues. After the complete blind pass, `prepare-adjudication`
verifies one stable reviewer identity, persists the immutable primary checksum, and routes
only flagged cases to metric-specific second-pass queues. `calibrate` rejects a changed primary
snapshot and fetches only the fully adjudicated approved label set before invoking either judge.
The accepted judge prompt/answer contract is the source-controlled
`shared-question-payload-v2-weighted-scores` revision, not an operator-supplied label. The rejected
`shared-question-payload-v3-score-anchors` experiment remains immutable diagnostic evidence and is
not a holdout prerequisite. Holdout requires the named, read-back-verified composite alignment
manifest for the exact label, rubric, evaluator, graph, accepted prompt, and source revisions; the
confirmation flag alone cannot bypass sequencing.

Real calibration calls are traced under `cam-41-alignment-*`. Every root must carry at least:

- `evidence_class=evaluator_alignment`;
- `experiment_purpose=alignment`;
- `alignment_run=true`;
- alignment or holdout split;
- dataset, label-set, rubric, evaluator, graph, prompt, code, judge, model, and provider revisions.

Missing metadata prevents publication or completion. The live workflow must read traces and feedback
back from LangSmith and verify discoverability, expected roots, three repetitions, both judges, every
question, and split coverage before reporting a completed run. A `--local-only` run requires a
non-empty untraced reason and can never satisfy completed alignment evidence.
The alignment-phase report is marked diagnostic even after successful read-back. Only a holdout
report with exactly seven questions, both judges, and seven recommendations can be marked complete.

Future release experiments use `evidence_class=release_experiment`,
`experiment_purpose=model_selection`, and `alignment_run=false`. Release selection excludes
`evidence_class=evaluator_alignment`, `experiment_purpose=alignment`, or `alignment_run=true` by
metadata rather than relying on a project-name prefix. Historical CAM-40 v2/v3 records keep their
original metadata and interpretation; they are not rewritten or relabeled as CAM-41 evidence.

Only sanitized aggregate results and per-question recommendations belong in the repository. Do not
commit labels, projected states, traces, downloaded result payloads, provider answers, credentials,
or private customer data.

LangSmith retains published datasets, queues, traces, and feedback according to workspace policy.
The live workspace showed 14-day base and 180-day extended retention; annotation-queue membership
and feedback trigger the extended tier, so selecting base as the project default does not keep this
workflow's evidence in the base tier.
TypeSafe zero data retention is not assumed. The MVP therefore permits only synthetic, sanitized
state in either system; production data requires a vendor/DPA, retention, and customer-data review.

OpenEvals was considered but is not adopted for this slice: the existing provider-neutral judge,
projection, rubric, and LangSmith contracts already express the required workflow, and another
dependency would not simplify human-preference alignment.

## 6. Presentation record

The presentation should show the lifecycle in this order: representative cases → blind human labels
→ frozen alignment labels → judge comparison and bounded rubric iteration → untouched holdout (not
run) → future recommendation. Report limitations beside the results, not as footnotes.

| Evidence | Required value |
| --- | --- |
| Label-set version | `cam-41-labels-v1` |
| Dataset/case revision | `freight-prospect-v1`; 70 selected cases read back |
| Rubric version evaluated | `semantic-v1` unless a frozen successor is recorded |
| Reviewer | `CAM-41 designated reviewer` (single reviewer) |
| Primary pass completion | Complete: 70/70 cases, 280/280 required fields; frozen 2026-10-01 |
| Second-pass completion | Complete: 13/13 flagged cases adjudicated |
| Approved reference set | `cam-41-labels-v1`; 70 examples (35 alignment, 35 holdout) |
| LangSmith alignment project/URL | [`cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed`](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/projects/p/809bfd2d-69b0-4dd2-b06a-2085506317ca); 210/210 roots and feedback read back |
| Code revision | `e270dd16365b-dirty-69c567eba5e0` |
| Aggregate report | [`backend/evaluation/reports/cam_41_diagnostics.md`](../../backend/evaluation/reports/cam_41_diagnostics.md) |
| Score-revision evidence | 60/60 combined valid attempts across [`cam-41-alignment-cam-41-labels-v1-9def2f19d5593cf7`](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/projects/p/a7f85072-13df-46e3-820e-08ef92772e32) and retry project [`cam-41-alignment-cam-41-labels-v1-4a7eedede417b378`](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/projects/p/beff5dd6-7291-40eb-96d1-c81361535374) |
| Score-revision report | [`backend/evaluation/reports/cam_41_score_revision_diagnostics.md`](../../backend/evaluation/reports/cam_41_score_revision_diagnostics.md) |
| Rejected v3 prompt experiment | [`cam-41-alignment-cam-41-labels-v1-b6adb9618f50cb3e`](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/projects/p/af6aa26e-1c6b-4da5-a165-3852133f9178); 60/60 valid attempts under `shared-question-payload-v3-score-anchors` |
| V3 diagnostic report | [`backend/evaluation/reports/cam_41_score_prompt_diagnostics.md`](../../backend/evaluation/reports/cam_41_score_prompt_diagnostics.md) |
| Accepted composite evidence | [`cam-41-alignment-composite-cam-41-labels-v1-039273d2fe8e3143`](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/projects/p/dd92223b-65df-44a7-ba7a-5940d7dd6e95); original categorical plus v2 score/retry sources; both prompt revisions pinned; 210 attempts read back |
| Alignment-only findings | Strong exact agreement: `claim_supported`, `internal_data_leak`, `next_step`, `entity_resolution_ok`; inspect before holdout: `draft_matches_brief`, `actionability`, `tone_fit` |

The earlier composite `cam-41-alignment-composite-cam-41-labels-v1-9ede43d8fc6305bc`
remains immutable but is superseded. Validation added categorical-prompt pinning and stricter stored
source-scope checks, producing the hardened project above as the only accepted holdout prerequisite.
The verifier additionally requires the exact approved categorical, v2-score, and unavailable-only
retry project names and their recorded code revisions; matching metadata from a substituted project
does not satisfy the holdout prerequisite.

The original alignment result has full persisted-attempt coverage but only 154/210 valid judge results.
All five binary/categorical questions have 100% valid coverage for both judges. Jev agreed exactly
on four and scored 80% on `draft_matches_brief`; GPT-5.6 Sol scored 100% on all five. After the
score-contract revision, `actionability` exact/within-one agreement is 60.0%/80.0% for Jev and
53.3%/93.3% for Sol; `tone_fit` is 60.0%/86.7% for Jev and 73.3%/93.3% for Sol. Jev is stable but
systematically under-scores some middle classes; Sol is closer on MAE but shows more run-to-run and
option-order variation. Both score questions need inspection before any holdout run. This is a
diagnostic finding, not a formal recommendation.
Under v3, Jev's `actionability` exact agreement improved to 66.7% and MAE to 0.483, but run-to-run
disagreement became 6.7% and option-order sensitivity became 20%; Jev `tone_fit` within-one fell to
80%. Sol also became less stable, including 40% and 66.7% option-order sensitivity on the two
questions. Because the acceptance rule prohibited reduced within-one agreement or new Jev
instability, v3 was rejected despite isolated improvements. The accepted composite manifest now
provides the fail-closed holdout prerequisite without rewriting any source project. The holdout is
intentionally unrun under the final take-home scope.

| V3 score question | Judge | Exact | MAE | Within one | Run-to-run disagreement | Option-order sensitivity |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `actionability` | Jev | 66.67% | 0.483 | 80.00% | 6.67% | 20.00% |
| `actionability` | GPT-5.6 Sol | 66.67% | 0.360 | 86.67% | 13.33% | 40.00% |
| `tone_fit` | Jev | 60.00% | 0.464 | 80.00% | 0.00% | 0.00% |
| `tone_fit` | GPT-5.6 Sol | 46.67% | 0.564 | 86.67% | 26.67% | 66.67% |

CAM-41 and CAM-50 are complete. Their human labels, alignment diagnostics, bounded v3 decision,
accepted composite, documentation, and verification evidence satisfy the take-home objective. This
completion does not represent a holdout result, semantic release gate, or production-readiness claim.

The immutable v2/v3 score traces were published before canonical score agreement was shared with
LangSmith feedback. Their per-run `cam41.human_agreement` score may therefore compare a fractional
weighted score literally even when the aggregate report maps it to the same nearest 1–5 label. The
composite uses feedback status and coverage, not that historical boolean score. Aggregate reports
are canonical for the completed alignment runs; future and holdout feedback now uses the same
nearest-label agreement function as reporting.

## 7. Package boundaries

The implementation is organized by lifecycle rather than as a flat live-script package:

- `reference/` owns deterministic cases, fixtures, human labels, feedback parsing, and freezes;
- `calibration/` owns attempts, execution contracts, metrics, summaries, and recommendation policy;
- `evidence/` owns provider-neutral trace and composite-manifest contracts;
- `integrations/langsmith/` owns datasets, queues, trace queries/publication, and manifest storage;
- `reporting/` owns sanitized aggregate validation and Markdown output; and
- `workflows/` coordinates labeling, calibration, and composite publication through injected clients.

The reference, calibration, and evidence layers do not import LangSmith clients, application
settings, provider construction, report writers, or network workflows. The CLI remains
`python -m evaluation.experiments.alignment`; the reorganization preserves seeds, identities,
hashes, report paths, trace metadata, authorization behavior, and existing evidence.

Current limitations and recalibration triggers:

- One reviewer cannot measure inter-rater agreement or broader stakeholder preference.
- Synthetic variant-compatible states may not represent customer-specific language, historical
  CAM-40 row state, or production drift.
- Recalibrate after a judge/model upgrade, rubric or projection change, material dataset change,
  class/distribution drift, repeated human disagreement, or newly approved customer examples.
- Before production data is used, complete provider retention/DPA review and customer-specific data
  approval.
