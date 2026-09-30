import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SOURCE_ROOT = path.resolve("src");
const SOURCE_EXTENSIONS = new Set([".css", ".svg", ".ts", ".tsx"]);
const checks = [
  [
    "raw color",
    /#[\da-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|lab|lch|color|color-mix|device-cmyk)\s*\(/giu,
  ],
  ["gradient", /\b(?:linear|radial|conic)-gradient\s*\(/giu],
  ["inline style", /\bstyle\s*=\s*[{"']/gu],
  ["arbitrary Tailwind value", /(?:[\w:/.-]+-\[[^\]\n]+\]|\[[^\]\n]+\]:)/gu],
];
const rawCssUnit = /\b\d*\.?\d+(?:px|r?em|ch|vh|vw|dvh|dvw|%)\b/giu;
const rawCssDeclaration = /(?:^|[;{])\s*(?:--[\w-]+|[a-z][\w-]*)\s*:/gmu;

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) return sourceFiles(target);
      return SOURCE_EXTENSIONS.has(path.extname(entry.name)) ? [target] : [];
    }),
  );
  return nested.flat();
}

export function findViolations(source, relative) {
  const failures = [];
  for (const [label, pattern] of checks) {
    for (const match of source.matchAll(pattern)) {
      const line = source.slice(0, match.index).split("\n").length;
      failures.push(`${relative}:${line}: ${label}: ${match[0]}`);
    }
  }
  if (path.extname(relative) === ".css") {
    for (const match of source.matchAll(rawCssUnit)) {
      const line = source.slice(0, match.index).split("\n").length;
      failures.push(`${relative}:${line}: raw CSS dimension: ${match[0]}`);
    }
    for (const match of source.matchAll(rawCssDeclaration)) {
      const line = source.slice(0, match.index).split("\n").length;
      failures.push(`${relative}:${line}: raw CSS declaration: ${match[0].trim()}`);
    }
  }
  return failures;
}

async function main() {
  const failures = [];
  for (const file of await sourceFiles(SOURCE_ROOT)) {
    const source = await readFile(file, "utf8");
    failures.push(...findViolations(source, path.relative(process.cwd(), file)));
  }

  if (failures.length > 0) {
    console.error("Tailwind policy violations:\n" + failures.join("\n"));
    process.exitCode = 1;
  } else {
    console.log("Tailwind policy passed: frontend source uses built-in utility values.");
  }
}

if (path.resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  await main();
}
