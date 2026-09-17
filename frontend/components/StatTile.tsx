export function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number | string;
  tone?: "default" | "success" | "warning" | "error";
}) {
  const toneClass = {
    default: "text-text-primary",
    success: "text-success",
    warning: "text-warning",
    error: "text-error",
  }[tone];

  return (
    <div className="border border-border bg-surface px-4 py-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`mt-1 font-mono text-2xl ${toneClass}`}>{value}</p>
    </div>
  );
}

/**
 * A horizontal count bar for the CURRENT (not historical) breakdown of a
 * value across a small set of categories -- e.g. jobs per channel. Built
 * from real counts already fetched by the page, not a charting library:
 * there is no time-series data anywhere in this system to justify one
 * (see Step 22 of the Phase 5 brief -- don't fabricate history that
 * doesn't exist), and a single current-snapshot bar doesn't need one.
 */
export function CountBar({
  segments,
}: {
  segments: { label: string; value: number; className: string }[];
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden border border-border">
        {total === 0 ? (
          <div className="w-full bg-surface-raised" />
        ) : (
          segments.map((s) => (
            <div
              key={s.label}
              className={s.className}
              style={{ width: `${(s.value / total) * 100}%` }}
              title={`${s.label}: ${s.value}`}
            />
          ))
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        {segments.map((s) => (
          <span key={s.label} className="font-mono">
            {s.label} {s.value}
          </span>
        ))}
      </div>
    </div>
  );
}
