import type { EventStatus, JobStatus } from "@/lib/types";

type Status = EventStatus | JobStatus;

// Each status gets a color AND a distinct marker shape/character -- never
// color alone, so the badge remains legible without color vision and in
// a terminal/screen-reader context. Labels use the raw backend status
// string (lowercase, underscored) rather than a prettified version, since
// this is an ops console where matching the actual persisted value is
// more useful than friendly copy.
const STATUS_STYLE: Record<Status, { color: string; marker: string }> = {
  received: { color: "text-text-secondary", marker: "○" },
  validated: { color: "text-text-secondary", marker: "○" },
  pending: { color: "text-text-secondary", marker: "○" },
  queued: { color: "text-accent", marker: "◐" },
  processing: { color: "text-accent", marker: "◑" },
  retrying: { color: "text-warning", marker: "↻" },
  delivered: { color: "text-success", marker: "●" },
  failed: { color: "text-error", marker: "✕" },
  dead_lettered: { color: "text-error", marker: "■" },
};

export function StatusBadge({ status }: { status: Status }) {
  const style = STATUS_STYLE[status] ?? { color: "text-text-secondary", marker: "?" };
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-xs ${style.color}`}
    >
      <span aria-hidden="true">{style.marker}</span>
      <span>{status}</span>
    </span>
  );
}
