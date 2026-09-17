import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  EmptyBlock,
  ErrorBlock,
  LoadingBlock,
  UnavailableBlock,
} from "../StateBlock";

describe("StateBlock components", () => {
  it("LoadingBlock announces a status role for assistive tech", () => {
    render(<LoadingBlock label="Loading events" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading events");
  });

  it("EmptyBlock is visually and textually distinct from an error", () => {
    render(<EmptyBlock title="No events match these filters" />);
    expect(screen.getByText("No events match these filters")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("UnavailableBlock explicitly says data is unavailable, not zero", () => {
    render(<UnavailableBlock context="Event list" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Event list is unavailable");
    expect(screen.getByText(/does not mean the system is idle/i)).toBeInTheDocument();
  });

  it("ErrorBlock surfaces the backend's machine-readable code", () => {
    render(<ErrorBlock code="EVENT_NOT_FOUND" message="No event found." />);
    expect(screen.getByRole("alert")).toHaveTextContent("EVENT_NOT_FOUND");
    expect(screen.getByText("No event found.")).toBeInTheDocument();
  });
});
