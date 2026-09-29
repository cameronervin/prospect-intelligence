---
name: frontend-design
description: Design or restyle frontend UI with product-specific art direction, accessible states, and browser verification. Skip behavior-only work that keeps the current visual language.
license: MIT
---

# Frontend Design

Build product UI, not a generic template. Follow the frontend rules and read
`docs/development/frontend-design.md` when present.

## Before coding

Inspect the affected UI, components, tokens, assets, and validation commands. Identify the user,
task, primary decision, content order, required states, and viewports. Follow any supplied design or
existing product language.

For a new surface or major restyle, define:

- **Thesis:** one sentence that ties the visual idea to the product and task.
- **System:** roles for color, type, spacing, density, radius, and motion.
- **Signature:** one repeated element taken from the product domain.
- **Avoid:** three template defaults that do not serve this product.

Do not create a second design system just to look different.

## Design rules

- Reuse the current components and tokens before adding styles or dependencies.
- Add a card or container only for required grouping, state, interaction, clipping, scrolling, or
  boundaries. Do not nest cards.
- Add labels, badges, pills, numbers, dividers, special edges, gradients, or shadows only when they
  explain taxonomy, state, sequence, hierarchy, or approved brand meaning.
- Use icons for clear navigation, controls, state, or entity recognition. Prefer text to decorative
  icons. Label unfamiliar icon-only controls and add a tooltip.
- Define display, body, utility, and numeric type roles. Do not change fonts without a product reason.
- Use motion for feedback, state changes, or spatial continuity. Respect reduced motion.
- Use real content. Show the working product instead of an unrequested marketing page.

## Build and verify

Start behavior changes with a focused failing component, accessibility, or end-to-end test.

After the first render:

1. **Subject swap:** revise choices that would fit an unrelated product unchanged.
2. **Deletion:** remove anything that does not improve meaning, grouping, state, use, or brand.
3. Inspect hierarchy, density, type, alignment, overflow, focus, contrast, and motion in the loading,
   empty, degraded, error, long-content, and success states in scope.

Use the Playwright MCP first and reuse its current session. Check relevant desktop and mobile views
and changed interactions. Use repository Playwright tests for repeatable behavior. Add visual
baselines only after the design is accepted.

Run the relevant local checks. Report the thesis, inspected views and states, and any limitation.
