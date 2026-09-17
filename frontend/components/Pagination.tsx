export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between border-t border-border pt-3 text-xs text-text-secondary">
      <span>
        {total === 0 ? "0 results" : `${start}–${end} of ${total}`}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="border border-border px-2 py-1 text-text-primary disabled:cursor-not-allowed disabled:opacity-40 hover:enabled:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          Previous
        </button>
        <span className="font-mono">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="border border-border px-2 py-1 text-text-primary disabled:cursor-not-allowed disabled:opacity-40 hover:enabled:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          Next
        </button>
      </div>
    </div>
  );
}
