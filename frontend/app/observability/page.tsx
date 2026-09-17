"use client";

import { api, type ApiResult } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { LoadingBlock, UnavailableBlock, ErrorBlock } from "@/components/StateBlock";
import { StatTile } from "@/components/StatTile";
import type { Channel, JobStatus, OpsOverviewResponse } from "@/lib/types";

const CHANNELS: Channel[] = ["email", "sms", "push"];

function sumStatus(data: OpsOverviewResponse, status: JobStatus): number {
  return CHANNELS.reduce(
    (total, channel) => total + (data.jobs_by_channel_and_status[channel]?.[status] ?? 0),
    0
  );
}

export default function ObservabilityPage() {
  const { data: result } = usePolling<ApiResult<OpsOverviewResponse>>(
    () => api.getOverview(),
    15000
  );

  return (
    <div className="max-w-4xl">
      <header className="mb-6">
        <h1 className="text-lg font-medium text-text-primary">Observability</h1>
        <p className="text-sm text-text-secondary">
          This page reads the same instrumentation Prometheus scrapes at{" "}
          <code className="font-mono text-text-tertiary">/metrics</code>, presented
          as a current snapshot. There is no time-series storage in Pulse
          today, so no throughput-over-time chart is shown here — that
          would have to be fabricated, and this dashboard does not do
          that. Wire a real Prometheus + Grafana stack to /metrics for
          historical graphs.
        </p>
      </header>

      {!result && <LoadingBlock label="Loading metrics" />}
      {result?.kind === "unavailable" && <UnavailableBlock context="Observability data" />}
      {result?.kind === "error" && (
        <ErrorBlock code={result.code} message={result.message} />
      )}

      {result?.kind === "ok" && (
        <div className="space-y-8">
          <section aria-labelledby="delivery-heading">
            <h2
              id="delivery-heading"
              className="mb-2 text-sm font-medium text-text-secondary"
            >
              Delivery (current totals across all channels)
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatTile
                label="Delivered"
                value={sumStatus(result.data, "delivered")}
                tone="success"
              />
              <StatTile
                label="Retrying"
                value={sumStatus(result.data, "retrying")}
                tone="warning"
              />
              <StatTile
                label="Dead-lettered"
                value={sumStatus(result.data, "dead_lettered")}
                tone="error"
              />
              <StatTile label="Queued" value={sumStatus(result.data, "queued")} />
              <StatTile label="Processing" value={sumStatus(result.data, "processing")} />
              <StatTile
                label="Failed (pre-retry)"
                value={sumStatus(result.data, "failed")}
                tone="error"
              />
            </div>
          </section>

          <section aria-labelledby="rate-limit-heading">
            <h2
              id="rate-limit-heading"
              className="mb-2 text-sm font-medium text-text-secondary"
            >
              Rate limit denials (this process, since last restart)
            </h2>
            <div className="grid grid-cols-3 gap-3">
              {CHANNELS.map((channel) => (
                <StatTile
                  key={channel}
                  label={channel}
                  value={result.data.rate_limit_denied_by_channel[channel]}
                  tone={
                    result.data.rate_limit_denied_by_channel[channel] > 0
                      ? "warning"
                      : "default"
                  }
                />
              ))}
            </div>
          </section>

          <section>
            <p className="border border-border bg-surface px-4 py-3 text-xs text-text-tertiary">
              {result.data.in_process_counters_note}
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
