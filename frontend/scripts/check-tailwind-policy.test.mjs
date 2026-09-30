import assert from "node:assert/strict";
import test from "node:test";

import { findViolations } from "./check-tailwind-policy.mjs";

test("accepts Tailwind built-in utilities and CSS composed with apply", () => {
  assert.deepEqual(
    findViolations(
      '<div className="min-h-11 rounded border border-slate-300 bg-white text-slate-950" />',
      "src/example.tsx",
    ),
    [],
  );
  assert.deepEqual(
    findViolations(".meter {\n  @apply h-1 rounded-full bg-slate-200;\n}", "src/example.css"),
    [],
  );
});

test("rejects raw styles and arbitrary Tailwind values", () => {
  const cases = [
    ["<div style={{ color: 'tomato' }} />", "inline style"],
    ['<div className="max-w-[68ch]" />', "arbitrary Tailwind value"],
    [".item { background: linear-gradient(white, black); }", "gradient"],
    [".item { color: lab(40% 56 39); }", "raw color"],
    [".item { --brand: tomato; }", "raw CSS declaration"],
    [".item { font-weight: 650; }", "raw CSS declaration"],
  ];

  for (const [source, expected] of cases) {
    assert.ok(
      findViolations(source, source.startsWith("<") ? "src/example.tsx" : "src/example.css").some(
        (failure) => failure.includes(expected),
      ),
      `expected ${expected} for ${source}`,
    );
  }
});
