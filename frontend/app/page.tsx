"use client";

import Link from "next/link";
import { api, type ApiResult } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { LoadingBlock, UnavailableBlock, ErrorBlock } from "@/components/StateBlock";
import { StatTile, CountBar } from "@/components/StatTile";
import type { Channel, OpsOverviewResponse } from "@/lib/types";

const CHANNELS: Channel[] = ["email", "sms", "push"];

const JOB_STATUS_CLASS: Record<string, string> = {
  delivered: "bg-success",
  processing: "bg-accent",
  queued: "bg-accent/50",
  retrying: "bg-warning",
  failed: "bg-error/60",
  dead_lettered: "bg-error",
  pending: "bg-text-tertiary",
};

export default function OverviewPage() {
  const { data: result } = usePolling<ApiResult<OpsOverviewResponse>>(
    () => api.getOverview(),
    15000
  );

  return (
    <div className="max-w-5xl">
      <header className="mb-6">
        <h1 className="text-lg font-medium text-text-primary">Overview</h1>
        <p className="text-sm text-text-secondary">
          System status and delivery counts. Refreshes every 15 seconds.
        </p>
      </header>

      {!result && <LoadingBlock label="Loading overview" />}
      {result?.kind === "unavailable" && <UnavailableBlock context="Overview" />}
      {result?.kind === "error" && (
        <ErrorBlock code={result.code} message={result.message} />
      )}

      {result?.kind === "ok" && (
        <div className="space-y-8">
          <section aria-labelledby="events-heading">
            <h2 id="events-heading" className="mb-2 text-sm font-medium text-text-secondary">
              Events
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile
                label="Delivered"
                value={result.data.events_by_status.delivered ?? 0}
                tone="success"
              />
              <StatTile
                label="Processing"
                value={
                  (result.data.events_by_status.processing ?? 0) +
                  (result.data.events_by_status.queued ?? 0)
                }
              />
              <StatTile
                label="Failed"
                value={result.data.events_by_status.failed ?? 0}
                tone="error"
              />
              <StatTile
                label="Dead-lettered jobs"
                value={result.data.dead_letter_count}
                tone={result.data.dead_letter_count > 0 ? "warning" : "default"}
              />
            </div>
          </section>

          <section aria-labelledby="channels-heading">
            <h2
              id="channels-heading"
              className="mb-2 text-sm font-medium text-text-secondary"
            >
              Jobs by channel
            </h2>
            <div className="space-y-4 border border-border bg-surface p-4">
              {CHANNELS.map((channel) => {
                const counts = result.data.jobs_by_channel_and_status[channel];
                const segments = Object.entries(counts)
                  .filter(([, value]) => value > 0)
                  .map(([status, value]) => ({
                    label: status,
                    value,
                    className: JOB_STATUS_CLASS[status] ?? "bg-text-tertiary",
                  }));
                return (
                  <div key={channel}>
                    <p className="mb-1 font-mono text-xs text-text-secondary">
                      {channel}
                    </p>
                    <CountBar segments={segments} />
                  </div>
                );
              })}
            </div>
          </section>

          <section aria-labelledby="rate-limit-heading">
            <h2
              id="rate-limit-heading"
              className="mb-2 text-sm font-medium text-text-secondary"
            >
              Rate limiting
            </h2>
            <p className="mb-2 text-xs text-text-tertiary">
              Redis-backed token bucket, enforced atomically per channel.
              Denial counts below are this API process&apos;s in-memory
              counters — they reset on restart and are not a durable
              historical total.
            </p>
            <div className="grid grid-cols-3 gap-3">
              {CHANNELS.map((channel) => (
                <div key={channel} className="border border-border bg-surface px-4 py-3">
                  <p className="font-mono text-xs text-text-secondary">{channel}</p>
                  <p className="mt-1 text-sm text-text-primary">
                    {result.data.configured_rate_limits_per_minute[channel]}/min configured
                  </p>
                  <p className="mt-1 font-mono text-xs text-text-tertiary">
                    {result.data.rate_limit_denied_by_channel[channel]} denied (this process)
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section>
            <Link
              href="/dead-letter"
              className="text-sm text-accent underline-offset-2 hover:underline"
            >
              Inspect dead-lettered jobs
            </Link>
          </section>
        </div>
      )}
    </div>
  );
}
