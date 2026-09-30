# Frontend design guidance

This document records the visual direction and UI-quality tooling that are appropriate for the
current take-home. It keeps active repository guidance separate from design-system work that would
be premature before the review UI is accepted.

## Current direction

The freight prospect experience should read as a **dispatch console**: quiet, operational, and built
for repeated scanning and review. The visual grammar should draw from route manifests and dispatch
work rather than a generic SaaS marketing page:

- compact, left-aligned hierarchy that exposes the working experience in the first viewport;
- flat true-white and cool-neutral surfaces, graphite text, thin dividers, and one restrained safety
  accent rather than decorative gradients or glows;
- small semantic radii, with pill geometry reserved for genuine status values;
- dense account, lane, evidence, and coverage rows instead of nested or repeated cards;
- explicit display, body, utility, and tabular-number typography roles;
- motion only for feedback, state change, or spatial continuity;
- a visibly emphasized human-review checkpoint because approval is the product's safety boundary.

The repository currently enforces the design workflow through `.agents/skills/frontend-design` and
the path-scoped frontend rules. Those instructions require product grounding, admission tests for
visual devices, subject-swap and deletion critiques, and Playwright MCP inspection at relevant
desktop and mobile viewports.

## Anti-template principles

Individual motifs are not inherently bad. They become generic when they appear without a content,
interaction, state, or brand reason.

- Eyebrows, kickers, badges, numbers, and dividers must communicate taxonomy, status, sequence, or
  hierarchy; they are not filler.
- Cards and containers must group independent objects, own interaction or state, clip or scroll
  content, or establish a necessary boundary. Do not nest cards.
- Icons must improve recognition of navigation, controls, state, or entities. Clear text is better
  than a decorative icon.
- Typography must fit the domain and content roles. Replacing one fashionable default with another
  is not art direction.
- A design that can be relabeled for an unrelated product without meaningful change has failed the
  subject-swap test.
- An element that can disappear without reducing comprehension, grouping, state, affordance, or
  brand meaning should be removed.

## Deferred design-system work

| Item                               | Current decision                                                                                | Activation condition                                                                                                                                        |
| ---------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Root `DESIGN.md`                   | Paused. Do not create a speculative token contract.                                             | CAM-36 establishes an approved and stable palette, typography, spacing, radius, component, and motion grammar worth preserving across agents and sessions.  |
| DTCG tokens and Style Dictionary   | Paused; CSS custom properties and Tailwind v4 theme variables are sufficient for the MVP.       | The product targets multiple platforms or needs generated token outputs beyond the web application.                                                         |
| `@shadcn/lint` component contracts | Paused. The current page has no shared UI component contract for `no-restyle` rules to protect. | A reusable component layer with approved variants exists; adopt only rules that match that contract and disclose the linter's limits.                       |
| Storybook                          | Paused. Component and Playwright tests are the smaller current workflow.                        | The frontend has a reusable component catalog with multiple meaningful visual states that is difficult to review through routes alone.                      |
| Committed screenshot baselines     | Paused so an unapproved scaffold does not become the golden design.                             | The CAM-36 cleanup is accepted; add stable desktop, mobile, and key-state baselines through CAM-37 in a pinned browser environment.                         |
| Figma MCP and Code Connect         | Paused because no maintained Figma source of truth exists.                                      | A reviewed Figma library becomes authoritative and its components can be mapped to repository components.                                                   |
| Headless primitive library         | No dependency now. Native HTML covers the present controls.                                     | A concrete accessible widget cannot be implemented clearly with native controls or an existing repository pattern; choose the narrowest suitable primitive. |
| Icon library                       | No dependency now. The current workflow does not need an icon vocabulary.                       | Repeated, familiar control or navigation symbols are approved; select one family and expose only the semantic project subset.                               |

Google's [`DESIGN.md` specification](https://github.com/google-labs-code/design.md),
[`@shadcn/lint`](https://github.com/shadcn-ui/lint),
[Storybook visual testing](https://storybook.js.org/docs/writing-tests/visual-testing), and
[Playwright visual comparisons](https://playwright.dev/docs/test-snapshots) are reference options,
not current dependencies. Re-evaluate them only when their activation conditions are met.

## CAM-36 handoff

CAM-36 owns the integrated visual cleanup for the brief, evidence, lane-fit, and outreach-review
experience. It should preserve CAM-35 behavior while replacing the current marketing and repeated-
card scaffold with the dispatch-console direction above. CAM-37 owns committed visual baselines and
expanded full-stack browser coverage after that direction is accepted.

### CAM-36 outcome

- **Thesis:** a dispatch manifest for one account. Every number sits beside its source, and nothing
  leaves without the rep's decision.
- **Layout:** decision-first. There are two panes on desktop, an accounts rail and one workspace,
  and a single column on mobile. While a decision is pending, the page leads with one accent-framed
  checkpoint: the outreach editor with large Approve / Reject actions beside a compact "Why this
  account" rationale. Lanes, assumptions and sources follow as supporting evidence. The outcome
  receipt, neutral outcomes and progress take the same top slot. The first design had a third,
  narrow review column; user review found the call to action unclear, so it was replaced.
- **System:** tokens live in `frontend/src/app/globals.css`:
  - white and `#f4f6f8` surfaces, graphite text, thin `#e1e5ea` dividers;
  - separate ready, degraded and danger colors;
  - one safety accent (`#c2410c`), used only on the review frame and its primary action.
- **Type roles:** self-hosted Archivo provides the `type-display`, `type-title`, `type-lead`,
  `type-section`, `type-body`, `type-utility` and `type-figure` roles. Tabular numerals are used for
  every figure.
- **Signature:** the lane manifest row (route, fit, matched loads, modeled revenue). Score
  components, volumes, deadhead and evidence open beneath the row instead of in a separate card.
- **Hierarchy:** verdict and recommended action lead, followed by two modeled totals. Assumptions,
  complete sources and non-lead lane details stay behind disclosures. Degraded and unavailable
  sources are always visible.
- **Reference:** the design canvas used for review (system, desktop, states and mobile boards) is a
  private claude.ai artifact. It is not a committed baseline; CAM-37 owns visual baselines.

