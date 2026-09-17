import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders the raw status text, not just a color", () => {
    render(<StatusBadge status="delivered" />);
    expect(screen.getByText("delivered")).toBeInTheDocument();
  });

  it("renders a distinct marker for each status so color is never the only signal", () => {
    const { rerender } = render(<StatusBadge status="delivered" />);
    const deliveredMarkup = document.body.innerHTML;

    rerender(<StatusBadge status="failed" />);
    const failedMarkup = document.body.innerHTML;

    expect(deliveredMarkup).not.toEqual(failedMarkup);
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("falls back gracefully for an unrecognized status rather than crashing", () => {
    // @ts-expect-error -- deliberately passing an invalid status to prove the fallback
    render(<StatusBadge status="totally_unknown_status" />);
    expect(screen.getByText("totally_unknown_status")).toBeInTheDocument();
  });
});
