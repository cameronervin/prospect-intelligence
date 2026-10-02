import { describe, expect, it } from "vitest";

import nextConfig, { buildContentSecurityPolicy } from "../../next.config";

describe("content security policy", () => {
  it("allows React development diagnostics without weakening production", () => {
    const development = buildContentSecurityPolicy(true);
    const production = buildContentSecurityPolicy(false);

    expect(development).toContain("script-src 'self' 'unsafe-inline' 'unsafe-eval'");
    expect(production).toContain("script-src 'self' 'unsafe-inline'");
    expect(production).not.toContain("'unsafe-eval'");
  });

  it("hides the Next.js development indicator", () => {
    expect(nextConfig.devIndicators).toBe(false);
  });

  it("allows the documented loopback origin to use development HMR", () => {
    expect(nextConfig.allowedDevOrigins).toEqual(["127.0.0.1"]);
  });
});
