import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("exposes the exact blocker without optimistic rewriting", () => {
    render(<StatusPill tone="warning">MEMORY DATA_DEFECT</StatusPill>);
    expect(screen.getByText("MEMORY DATA_DEFECT")).toHaveClass(
      "status",
      "warning",
    );
  });
});
