import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "@/components/brand-mark";

describe("BrandMark", () => {
  it("renders a decorative resolution-independent semi-truck mark", () => {
    const { container } = render(<BrandMark />);
    const mark = container.querySelector("svg");

    expect(mark).toHaveAttribute("aria-hidden", "true");
    expect(mark).toHaveAttribute("viewBox", "0 0 96 64");
    expect(mark).not.toHaveAttribute("width");
    expect(mark).not.toHaveAttribute("height");
    expect(container.querySelector('[data-part="trailer"]')).toBeInTheDocument();
    expect(container.querySelector('[data-part="cab"]')).toBeInTheDocument();
  });
});
