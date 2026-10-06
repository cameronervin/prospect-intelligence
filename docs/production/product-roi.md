# Product ROI

## Recommendation

Continue to a controlled sales pilot. Do not approve autonomous outreach or a broad production
rollout yet.

The base case estimates **$2.36 million in first-year gross sales** and **$283,000 in contribution
margin** from about **35 won lane opportunities**. Estimated recurring product cost is **$90,000 per
year**. This is a 26x gross-sales-to-spend ratio and a 3.1x contribution-to-spend ratio.

These figures are a decision model, not a revenue forecast. The pilot must measure incremental wins
against comparable accounts that do not use the product.

## Base case

The client already owns GenLogs, its CRM, and carrier-network data. The model assumes 25 sales
representatives analyze 20 accounts per week for 48 weeks.

| Funnel stage | Assumption | Annual result |
| --- | ---: | ---: |
| Completed analyses | `25 reps × 20 accounts × 48 weeks` | 24,000 |
| High-fit accounts | 20% | 4,800 |
| Rep-approved outreach | 60% | 2,880 |
| Meetings | 8% | 230 |
| Won lane opportunities | 15% | 35 |

The synthetic evaluation dataset has a median modeled annual revenue of $273,000 for its top lane
among fit cases. The ROI model recognizes only 25% of that amount in the first year to allow for a
partial award, ramp time, and lower realized volume.

- First-year sales per win: `$273,000 × 25% = $68,250`
- Assumed contribution margin: 12%
- First-year contribution per win: `$68,250 × 12% = $8,190`
- Expected gross sales: `34.56 wins × $68,250 = $2,358,720`
- Expected contribution: `34.56 wins × $8,190 = $283,046`

The $273,000 value comes from synthetic opportunity estimates. It is not booked revenue, guaranteed
volume, or a customer-specific forecast.

## Product cost

| Recurring cost | Annual estimate |
| --- | ---: |
| Model inference, including an allowance for observed failed runs | $7,600 |
| Application hosting, PostgreSQL, LangSmith, and monitoring | $18,000 |
| 0.25 loaded engineering and operations FTE | $50,000 |
| Three-minute review of each high-fit result at $60 per hour | $14,400 |
| **Total recurring cost** | **$90,000** |

The inference estimate starts with the CAM-40 baseline cost of $0.294620 per run. Adjusting for its
5 target errors in 72 runs gives about $0.317 per completed analysis, or $7,600 for 24,000 analyses.

Add an estimated $80,000 for first-year hardening, security work, deployment, and integration. This
makes total first-year product spend about $170,000. Existing CRM, GenLogs, and carrier data costs
are excluded by assumption.

The $80,000 is an effort estimate, not a quote. It assumes the team builds with agentic coding tools,
and it prices engineering at about $200,000 per loaded FTE-year (about $4,000 per week), the same rate
behind the 0.25 FTE line above. Agentic tools compress coding, not the dependencies: client IT setup
for SSO, data access and field mapping, and the external security review still set a pilot start
about two to three months out. A conventional estimate was about 27.5 engineer-weeks, or $125,000.

| One-time workstream | Effort | Estimate |
| --- | ---: | ---: |
| Enterprise SSO and row-level security | 3 engineer-weeks | $12,000 |
| LangSmith Deployment, message queue, and once-only sends | 3 engineer-weeks | $12,000 |
| Guardrails: sandboxed code, gateway PII rules, Jev calibration | 3 engineer-weeks | $12,000 |
| Real CRM, GenLogs, and carrier-network connections | 6 engineer-weeks | $24,000 |
| Pilot evaluation set and monitoring setup | 1 engineer-week | $4,000 |
| External security review | Fixed fee | $16,000 |
| **Total** | **16 engineer-weeks + review** | **$80,000** |

| Measure | Recurring | First year |
| --- | ---: | ---: |
| Gross sales / product spend | 26x | 14x |
| Contribution / product spend | 3.1x | 1.7x |
| Product spend per won lane | $2,600 | $4,900 |
| Incremental wins required to break even | 11 | 21 |

Research-time savings are excluded to avoid counting the same benefit twice. They would be
additional upside.

## Evaluation evidence

The CAM-40 LangSmith experiment supports testing this case in a pilot:

- The selected baseline scored about 93% on lane choice, verdict, workflow trajectory, and injection
  resistance, with 99.4% file-contract compliance.
- The baseline had 5 target errors in 72 runs. Lower-cost routing had 21 errors in 72 runs and lower
  quality scores.
- The prompt revision cost 12.2% more without a meaningful quality improvement.
- Removing the interpreter did not improve quality, latency, or cost per usable result.
- Human approval remains mandatory before any simulated outreach action.

The evidence does not establish production readiness. The dataset is synthetic, the numeric
grounding result remains diagnostic, the semantic holdout is unrun, and real conversion uplift has
not been measured. See the [CAM-40 hosted report](../../backend/evaluation/reports/cam_40_hosted.md)
and [experiment decision](../evaluation/experimentation-process.md).

## Pilot decision

Run an 8- to 12-week pilot with matched non-agent accounts. Measure the full funnel from analysis to
realized loads. Count only the difference from the comparison group as incremental value.

Continue to broader deployment only when:

- annualized incremental contribution is at least 2x recurring product cost;
- expected first-year payback is 12 months or less;
- results support at least 11 incremental annual wins at steady state; and
- numeric grounding and customer-facing safety remain within approved limits.

This supports a pilot investment. It does not support autonomous sending, guaranteed revenue, or a
production-wide rollout.
