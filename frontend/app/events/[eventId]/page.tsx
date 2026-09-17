"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type ApiResult } from "@/lib/api";
import { LoadingBlock, UnavailableBlock, ErrorBlock } from "@/components/StateBlock";
import { StatusBadge } from "@/components/StatusBadge";
import type { EventResponse, JobDetailResponse } from "@/lib/types";

// The actual persisted lifecycle, not an idealized one -- matches
// app/core/states.py's EVENT_TRANSITIONS exactly. Shown as a static
// reference alongside the event's current (real) status badge, not as
// an animated progress bar implying steps not actually observed.
const EVENT_LIFECYCLE = [
  "received",
  "validated",
  "queued",
  "processing",
  "delivered",
];

export default function EventDetailPage() {
  const params = useParams<{ eventId: string }>();
  const eventId = decodeURIComponent(params.eventId);
  const [result, setResult] = useState<ApiResult<EventResponse> | null>(null);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<
    Record<string, ApiResult<JobDetailResponse>>
  >({});

  useEffect(() => {
    api.getEvent(eventId).then(setResult);
  }, [eventId]);

  async function toggleJob(jobId: string) {
    if (expandedJob === jobId) {
      setExpandedJob(null);
      return;
    }
    setExpandedJob(jobId);
    if (!jobDetail[jobId]) {
      const detail = await api.getJob(jobId);
      setJobDetail((prev) => ({ ...prev, [jobId]: detail }));
    }
  }

  return (
    <div className="max-w-3xl">
      <header className="mb-6">
        <p className="font-mono text-xs text-text-tertiary">{eventId}</p>
        <h1 className="text-lg font-medium text-text-primary">Event detail</h1>
      </header>

      {!result && <LoadingBlock label="Loading event" />}
      {result?.kind === "unavailable" && <UnavailableBlock context="Event detail" />}
      {result?.kind === "error" && (
        <ErrorBlock code={result.code} message={result.message} />
      )}

      {result?.kind === "ok" && (
        <div className="space-y-6">
          <section className="border border-border bg-surface p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-text-primary">{result.data.event_type}</p>
                <p className="mt-1 font-mono text-xs text-text-tertiary">
                  Created {new Date(result.data.created_at).toLocaleString()}
                </p>
              </div>
              <StatusBadge status={result.data.status} />
            </div>
            <div className="mt-4 flex flex-wrap gap-1 font-mono text-xs text-text-tertiary">
              {EVENT_LIFECYCLE.map((step, i) => (
                <span key={step} className="flex items-center gap-1">
                  <span
                    className={
                      step === result.data.status
                        ? "text-text-primary"
                        : "text-text-tertiary"
                    }
                  >
                    {step}
                  </span>
                  {i < EVENT_LIFECYCLE.length - 1 && <span aria-hidden="true">/</span>}
                </span>
              ))}
              {(result.data.status === "failed" ||
                result.data.status === "dead_lettered") && (
                <span className="text-error">/ {result.data.status}</span>
              )}
            </div>
          </section>

          <section aria-labelledby="jobs-heading">
            <h2 id="jobs-heading" className="mb-2 text-sm font-medium text-text-secondary">
              Notification jobs
            </h2>
            <div className="divide-y divide-border border border-border bg-surface">
              {result.data.jobs.map((job) => (
                <div key={job.job_id}>
                  <button
                    type="button"
                    onClick={() => toggleJob(job.job_id)}
                    aria-expanded={expandedJob === job.job_id}
                    className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                  >
                    <span className="font-mono text-xs text-text-primary">
                      {job.channel}
                    </span>
                    <span className="flex items-center gap-4">
                      <span className="text-xs text-text-tertiary">
                        attempt {job.attempt_count}
                      </span>
                      <StatusBadge status={job.status} />
                    </span>
                  </button>

                  {expandedJob === job.job_id && (
                    <div className="border-t border-border bg-bg px-4 py-3">
                      {!jobDetail[job.job_id] && <LoadingBlock label="Loading job" />}
                      {jobDetail[job.job_id]?.kind === "unavailable" && (
                        <UnavailableBlock context="Job detail" />
                      )}
                      {jobDetail[job.job_id]?.kind === "error" && (
                        <ErrorBlock
                          code={(jobDetail[job.job_id] as { code: string }).code}
                          message={(jobDetail[job.job_id] as { message: string }).message}
                        />
                      )}
                      {jobDetail[job.job_id]?.kind === "ok" && (
                        <JobDetailPanel
                          detail={(jobDetail[job.job_id] as { data: JobDetailResponse }).data}
                        />
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function JobDetailPanel({ detail }: { detail: JobDetailResponse }) {
  return (
    <div className="space-y-3 text-xs">
      <dl className="grid grid-cols-2 gap-2 font-mono text-text-secondary sm:grid-cols-4">
        <div>
          <dt className="text-text-tertiary">Max attempts</dt>
          <dd className="text-text-primary">{detail.max_attempts}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">Claimed at</dt>
          <dd className="text-text-primary">
            {detail.claimed_at ? new Date(detail.claimed_at).toLocaleString() : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-text-tertiary">Lease expires</dt>
          <dd className="text-text-primary">
            {detail.lease_expires_at
              ? new Date(detail.lease_expires_at).toLocaleString()
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-text-tertiary">Next scheduled</dt>
          <dd className="text-text-primary">
            {detail.scheduled_at ? new Date(detail.scheduled_at).toLocaleString() : "—"}
          </dd>
        </div>
      </dl>

      {detail.last_error && (
        <p className="border border-error/40 bg-error/10 px-3 py-2 text-error">
          {detail.last_error}
        </p>
      )}

      <div>
        <p className="mb-1 text-text-tertiary">Delivery attempts</p>
        {detail.deliveries.length === 0 ? (
          <p className="text-text-tertiary">No delivery attempts recorded yet.</p>
        ) : (
          <table className="text-xs">
            <thead>
              <tr className="text-text-tertiary">
                <th className="py-1 pr-3">Provider</th>
                <th className="py-1 pr-3">Status</th>
                <th className="py-1 pr-3">Attempted</th>
                <th className="py-1 pr-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {detail.deliveries.map((d, i) => (
                <tr key={i} className="text-text-secondary">
                  <td className="py-1 pr-3 font-mono">{d.provider}</td>
                  <td className="py-1 pr-3 font-mono">{d.status}</td>
                  <td className="py-1 pr-3 font-mono">
                    {new Date(d.attempted_at).toLocaleTimeString()}
                  </td>
                  <td className="py-1 pr-3 text-error">{d.error_message ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
