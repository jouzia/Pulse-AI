import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import OverviewPage from "../page";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    getOverview: vi.fn(),
  },
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("OverviewPage", () => {
  it("shows a loading state before data arrives", () => {
    vi.mocked(api.getOverview).mockReturnValue(new Promise(() => {}));
    render(<OverviewPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an explicit unavailable state rather than a zero count", async () => {
    vi.mocked(api.getOverview).mockResolvedValue({ kind: "unavailable" });
    render(<OverviewPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Overview is unavailable");
    });
    // Critically: no stat tiles claiming "0" should render alongside this.
    expect(screen.queryByText("Delivered")).not.toBeInTheDocument();
  });

  it("shows the backend error code when the backend responds with an error", async () => {
    vi.mocked(api.getOverview).mockResolvedValue({
      kind: "error",
      status: 500,
      code: "INTERNAL_ERROR",
      message: "An unexpected error occurred.",
    });
    render(<OverviewPage />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("INTERNAL_ERROR");
    });
  });

  it("renders real counts when data is available", async () => {
    const zeroJobCounts = {
      pending: 0,
      queued: 0,
      processing: 0,
      delivered: 0,
      failed: 0,
      retrying: 0,
      dead_lettered: 0,
    };
    vi.mocked(api.getOverview).mockResolvedValue({
      kind: "ok",
      data: {
        events_by_status: {
          received: 0,
          validated: 0,
          queued: 0,
          processing: 0,
          delivered: 3,
          failed: 1,
          dead_lettered: 0,
        },
        jobs_by_channel_and_status: {
          email: { ...zeroJobCounts, delivered: 2 },
          sms: { ...zeroJobCounts, retrying: 1 },
          push: { ...zeroJobCounts },
        },
        dead_letter_count: 0,
        rate_limit_denied_total: 0,
        rate_limit_denied_by_channel: { email: 0, sms: 0, push: 0 },
        configured_rate_limits_per_minute: { email: 100, sms: 30, push: 200 },
        in_process_counters_note: "note",
      },
    });
    render(<OverviewPage />);
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });
});
