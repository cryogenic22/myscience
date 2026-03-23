interface SearchPaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
}

export default function SearchPagination({
  page,
  totalPages,
  onPageChange,
  disabled = false,
}: SearchPaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-md"
      style={{
        padding: '4px 6px',
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}
    >
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1 || disabled}
        className="rounded-md text-xs transition-colors disabled:opacity-40"
        style={{ padding: '4px 12px', color: 'var(--color-ink-2)' }}
      >
        Prev
      </button>
      <span className="text-[11px]" style={{ padding: '0 4px', color: 'var(--color-ink-3)' }}>
        Page {page}/{totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages || disabled}
        className="rounded-md text-xs transition-colors disabled:opacity-40"
        style={{ padding: '4px 12px', color: 'var(--color-ink-2)' }}
      >
        Next
      </button>
    </div>
  );
}
