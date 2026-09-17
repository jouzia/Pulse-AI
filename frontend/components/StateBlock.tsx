/**
 * Every view that fetches data renders exactly one of these four states,
 * never a fake stand-in for one of the others:
 *
 *   - Loading:     request in flight
 *   - Empty:       backend reached successfully, zero records exist
 *   - Unavailable: backend/proxy could not be reached at all
 *   - Error:       backend reached, but returned an error response
 *
 * Collapsing "unavailable" or "error" into a 0 count or a blank table
 * would be misleading observability -- indistinguishable from "the
 * system is healthy and idle." See lib/api.ts's ApiResult type, which is
 * what forces callers to handle these separately rather than defaulting.
 */

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex items-center gap-2 py-8 text-sm text-text-tertiary"
    >
      <span
        aria-hidden="true"
        className="h-3 w-3 animate-pulse rounded-full bg-text-tertiary"
      />
      {label}…
    </div>
  );
}

export function EmptyBlock({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="border border-dashed border-border py-10 text-center">
      <p className="text-sm text-text-secondary">{title}</p>
      {description && (
        <p className="mt-1 text-xs text-text-tertiary">{description}</p>
      )}
    </div>
  );
}

export function UnavailableBlock({ context }: { context: string }) {
  return (
    <div
      role="alert"
      className="border border-error/40 bg-error/10 px-4 py-4 text-sm text-error"
    >
      <p className="font-medium">{context} is unavailable</p>
      <p className="mt-1 text-xs text-error/80">
        The Pulse API could not be reached. This does not mean the system is
        idle — it means this dashboard has no current information.
      </p>
    </div>
  );
}

export function ErrorBlock({ code, message }: { code: string; message: string }) {
  return (
    <div
      role="alert"
      className="border border-error/40 bg-error/10 px-4 py-4 text-sm text-error"
    >
      <p className="font-medium font-mono">{code}</p>
      <p className="mt-1 text-xs text-error/80">{message}</p>
    </div>
  );
}
