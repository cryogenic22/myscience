import { useCallback, useMemo, useState } from 'react';

export interface DataTableColumn {
  key: string;
  label: string;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  width?: string;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  rows: Record<string, unknown>[];
  onRowClick?: (row: Record<string, unknown>) => void;
  defaultSort?: { key: string; direction: 'asc' | 'desc' };
  maxHeight?: string;
}

type SortDir = 'asc' | 'desc';

function compareValues(a: unknown, b: unknown, dir: SortDir): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  const numA = Number(a);
  const numB = Number(b);
  if (Number.isFinite(numA) && Number.isFinite(numB)) {
    return dir === 'asc' ? numA - numB : numB - numA;
  }

  const strA = String(a).toLowerCase();
  const strB = String(b).toLowerCase();
  const cmp = strA.localeCompare(strB);
  return dir === 'asc' ? cmp : -cmp;
}

export function DataTable({
  columns,
  rows,
  onRowClick,
  defaultSort,
  maxHeight = '400px',
}: DataTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(defaultSort?.key ?? null);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSort?.direction ?? 'asc');

  const handleHeaderClick = useCallback((col: DataTableColumn) => {
    if (!col.sortable) return;
    if (sortKey === col.key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(col.key);
      setSortDir('asc');
    }
  }, [sortKey]);

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => compareValues(a[sortKey], b[sortKey], sortDir));
  }, [rows, sortKey, sortDir]);

  return (
    <div
      style={{
        borderRadius: '12px',
        overflow: 'hidden',
        border: '1px solid var(--color-line)',
      }}
    >
      <div
        style={{
          overflowX: 'auto',
          maxHeight,
        }}
      >
        <table
          style={{
            width: '100%',
            fontSize: '13px',
            borderCollapse: 'collapse',
          }}
        >
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleHeaderClick(col)}
                  style={{
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                    textAlign: col.align ?? 'left',
                    fontSize: '11px',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    color: 'var(--color-ink-3)',
                    padding: '8px 12px',
                    background: 'var(--color-surface-2)',
                    borderBottom: '1px solid var(--color-divider-2)',
                    cursor: col.sortable ? 'pointer' : 'default',
                    whiteSpace: 'nowrap',
                    userSelect: 'none',
                    width: col.width,
                  }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    {col.label}
                    {col.sortable && sortKey === col.key && (
                      <span style={{ fontSize: '10px', opacity: 0.7 }}>
                        {sortDir === 'asc' ? '\u25B2' : '\u25BC'}
                      </span>
                    )}
                    {col.sortable && sortKey !== col.key && (
                      <span style={{ fontSize: '10px', opacity: 0.3 }}>
                        {'\u25B2'}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick?.(row)}
                style={{
                  cursor: onRowClick ? 'pointer' : 'default',
                  transition: 'background 100ms ease',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = 'var(--color-surface-2)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = 'transparent';
                }}
              >
                {columns.map((col, ci) => (
                  <td
                    key={col.key}
                    style={{
                      padding: '10px 12px',
                      textAlign: col.align ?? 'left',
                      fontWeight: ci === 0 ? 500 : 400,
                      color: ci === 0 ? 'var(--color-ink)' : 'var(--color-ink-2)',
                      borderBottom: i < sortedRows.length - 1 ? '1px solid var(--color-line-2)' : 'none',
                    }}
                  >
                    {row[col.key] != null ? String(row[col.key]) : '\u2014'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
