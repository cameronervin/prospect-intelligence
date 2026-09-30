import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("application favicon", () => {
  it("ships a non-empty Windows icon for browser fallback requests", async () => {
    const favicon = await readFile(path.resolve(process.cwd(), "src/app/favicon.ico"));

    expect([...favicon.subarray(0, 4)]).toEqual([0, 0, 1, 0]);
    expect(favicon.byteLength).toBeGreaterThan(512);
  });
});
