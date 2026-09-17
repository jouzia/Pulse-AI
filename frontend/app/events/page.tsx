"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ApiResult } from "@/lib/api";
import { LoadingBlock, EmptyBlock, UnavailableBlock, ErrorBlock } from "@/components/StateBlock";
import { StatusBadge } from "@/components/StatusBadge";
import { Pagination } from "@/components/Pagination";
import type { EventListResponse, EventStatus } from "@/lib/types";

const PAGE_SIZE = 25;
const STATUS_OPTIONS: EventStatus[] = [
  "received",
  "validated",
  "queued",
  "processing",
  "delivered",
  "failed",
  "dead_lettered",
];

export default function EventsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("");
  const [eventType, setEventType] = useState<string>("");
  const [result, setResult] = useState<ApiResult<EventListResponse> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    api
      .listEvents({
        page,
        page_size: PAGE_SIZE,
        status: status || undefined,
        event_type: eventType || undefined,
      })
      .then((r) => {
        if (!cancelled) setResult(r);
      });
    return () => {
      cancelled = true;
    };
  }, [page, status, eventType]);

  return (
    <div className="max-w-5xl">
      <header className="mb-6">
        <h1 className="text-lg font-medium text-text-primary">Events</h1>
        <p className="text-sm text-text-secondary">
          All events received via POST /api/v1/events, filterable by status and
          event type.
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-text-secondary">
          Status
          <select
            value={status}
            onChange={(e) => {
              setPage(1);
              setStatus(e.target.value);
            }}
            className="border border-border bg-surface px-2 py-1 text-sm text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-secondary">
          Event type
          <input
            type="text"
            value={eventType}
            onChange={(e) => {
              setPage(1);
              setEventType(e.target.value);
            }}
            placeholder="payment.succeeded"
            className="border border-border bg-surface px-2 py-1 text-sm text-text-primary placeholder:text-text-tertiary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          />
        </label>
      </div>

      {!result && <LoadingBlock label="Loading events" />}
      {result?.kind === "unavailable" && <UnavailableBlock context="Event list" />}
      {result?.kind === "error" && (
        <ErrorBlock code={result.code} message={result.message} />
      )}
      {result?.kind === "ok" && result.data.items.length === 0 && (
        <EmptyBlock
          title="No events match these filters"
          description="Backend was reached successfully — there are simply no matching rows."
        />
      )}
      {result?.kind === "ok" && result.data.items.length > 0 && (
        <div className="space-y-3">
          <table className="text-sm">
            <thead>
              <tr className="border-b border-border text-text-secondary">
                <th className="py-2 pr-4">Event ID</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Created</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((event) => (
                <tr key={event.event_id} className="border-b border-border/50">
                  <td className="py-2 pr-4 font-mono text-xs">
                    <Link
                      href={`/events/${encodeURIComponent(event.event_id)}`}
                      className="text-accent hover:underline"
                    >
                      {event.event_id}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 text-text-primary">{event.event_type}</td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={event.status} />
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-secondary">
                    {new Date(event.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            page={result.data.page}
            pageSize={result.data.page_size}
            total={result.data.total}
            onPageChange={setPage}
          />
        </div>
      )}
    </div>
  );
}
