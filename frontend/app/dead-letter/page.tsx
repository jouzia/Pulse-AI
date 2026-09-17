"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ApiResult } from "@/lib/api";
import { LoadingBlock, EmptyBlock, UnavailableBlock, ErrorBlock } from "@/components/StateBlock";
import { Pagination } from "@/components/Pagination";
import type { DeadLetterListResponse } from "@/lib/types";

const PAGE_SIZE = 25;

export default function DeadLetterPage() {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ApiResult<DeadLetterListResponse> | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);

  function load() {
    setResult(null);
    api.listDeadLetter({ page, page_size: PAGE_SIZE }).then(setResult);
  }

  useEffect(load, [page]);

  async function handleRetry(id: string) {
    setRetrying(id);
    setRetryMessage(null);
    const outcome = await api.retryDeadLetter(id);
    setRetrying(null);
    if (outcome.kind === "ok") {
      setRetryMessage(`Requeued job ${outcome.data.job_id} (${outcome.data.channel}).`);
      load();
    } else if (outcome.kind === "error") {
      setRetryMessage(`Retry failed: ${outcome.message}`);
    } else {
      setRetryMessage("Retry failed: backend unavailable.");
    }
  }

  return (
    <div className="max-w-4xl">
      <header className="mb-6">
        <h1 className="text-lg font-medium text-text-primary">Dead letter</h1>
        <p className="text-sm text-text-secondary">
          Jobs that exhausted their retry budget. Retrying here resets the
          attempt count and re-enters the job through normal processing — it
          is a deliberate, authenticated action, not a silent state change.
        </p>
      </header>

      {retryMessage && (
        <p className="mb-4 border border-border bg-surface px-3 py-2 text-xs text-text-secondary">
          {retryMessage}
        </p>
      )}

      {!result && <LoadingBlock label="Loading dead-letter queue" />}
      {result?.kind === "unavailable" && <UnavailableBlock context="Dead-letter queue" />}
      {result?.kind === "error" && (
        <ErrorBlock code={result.code} message={result.message} />
      )}
      {result?.kind === "ok" && result.data.items.length === 0 && (
        <EmptyBlock
          title="No dead-lettered jobs"
          description="Backend was reached successfully — the dead-letter queue is empty."
        />
      )}
      {result?.kind === "ok" && result.data.items.length > 0 && (
        <div className="space-y-3">
          <table className="text-sm">
            <thead>
              <tr className="border-b border-border text-text-secondary">
                <th className="py-2 pr-4">Event</th>
                <th className="py-2 pr-4">Channel</th>
                <th className="py-2 pr-4">Attempts</th>
                <th className="py-2 pr-4">Reason</th>
                <th className="py-2 pr-4">Failed at</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((item) => (
                <tr key={item.id} className="border-b border-border/50">
                  <td className="py-2 pr-4 font-mono text-xs">
                    <Link
                      href={`/events/${encodeURIComponent(item.event_id)}`}
                      className="text-accent hover:underline"
                    >
                      {item.event_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-primary">
                    {item.channel}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-secondary">
                    {item.attempt_count}
                  </td>
                  <td className="max-w-xs truncate py-2 pr-4 text-xs text-error" title={item.reason}>
                    {item.reason}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-secondary">
                    {new Date(item.failed_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-xs">
                    {item.resolved_at ? (
                      <span className="text-success">retried</span>
                    ) : (
                      <span className="text-error">unresolved</span>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    {!item.resolved_at && (
                      <button
                        type="button"
                        onClick={() => handleRetry(item.id)}
                        disabled={retrying === item.id}
                        className="border border-border px-2 py-1 text-xs text-text-primary hover:enabled:border-accent disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                      >
                        {retrying === item.id ? "Retrying…" : "Retry"}
                      </button>
                    )}
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
