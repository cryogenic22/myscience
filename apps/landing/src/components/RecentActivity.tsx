import { Pill } from '@pulse/ui';

interface ActivityRow {
  id: string;
  module: 'ci' | 'research' | 'regulatory';
  title: string;
  meta: string;
  time: string;
}

const MOCK: ActivityRow[] = [
  { id: '1', module: 'ci',       title: 'Pfizer 8-K Item 5.02 — CMO transition',         meta: 'CONFIRMED · HIGH IMPACT', time: '2h ago' },
  { id: '2', module: 'research', title: '"Tirzepatide MACE outcomes" research run',     meta: 'completed · 14 sources',  time: '4h ago' },
  { id: '3', module: 'ci',       title: 'Novo CHMP positive opinion for semaglutide',   meta: 'CONFIRMED · MEDIUM',      time: '6h ago' },
  { id: '4', module: 'ci',       title: 'BMS 8-K Item 1.01 — license-in deal · KRAS',   meta: 'CONFIRMED · HIGH IMPACT', time: '9h ago' },
  { id: '5', module: 'research', title: '"GLP-1 cardio outcomes meta-analysis" query',  meta: 'completed · 22 sources',  time: '11h ago' },
];

export function RecentActivity() {
  return (
    <ul
      role="list"
      style={{
        listStyle: 'none',
        margin: 0,
        padding: 0,
      }}
    >
      {MOCK.map((row, i) => (
        <li
          key={row.id}
          style={{
            display: 'grid',
            gridTemplateColumns: '88px 1fr auto',
            alignItems: 'center',
            gap: 'var(--mz-space-3)',
            padding: 'var(--mz-space-3) var(--mz-space-4)',
            borderTop: i === 0 ? 'none' : '1px solid var(--mz-color-border-subtle)',
          }}
        >
          <Pill
            tone="accent"
            subtle
            size="sm"
          >
            <span data-module={row.module} style={{ color: 'var(--mz-color-accent)' }}>
              {row.module.toUpperCase()}
            </span>
          </Pill>
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 'var(--mz-text-body-2)',
                color: 'var(--mz-color-text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {row.title}
            </div>
            <div
              style={{
                fontFamily: 'var(--mz-font-mono)',
                fontSize: 'var(--mz-text-mono-3)',
                color: 'var(--mz-color-text-tertiary)',
                letterSpacing: 'var(--mz-tracking-wide)',
                marginTop: 2,
              }}
            >
              {row.meta}
            </div>
          </div>
          <span
            style={{
              fontSize: 'var(--mz-text-body-3)',
              color: 'var(--mz-color-text-tertiary)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {row.time}
          </span>
        </li>
      ))}
    </ul>
  );
}
