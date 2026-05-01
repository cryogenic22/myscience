import { useState } from 'react';
import type { ConnectorDetail } from '../../api';
import ConnectorOverviewTab from './ConnectorOverviewTab';
import ConnectorPermissionsTab from './ConnectorPermissionsTab';
import ConnectorHealthTab from './ConnectorHealthTab';

interface Props {
  detail: ConnectorDetail;
  onChanged: () => void;
}

type TabKey = 'overview' | 'permissions' | 'health';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'permissions', label: 'Permissions' },
  { key: 'health', label: 'Health' },
];

export default function ConnectorDetailView({ detail, onChanged }: Props) {
  const [tab, setTab] = useState<TabKey>('overview');

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <div className="flex items-center gap-3" style={{ marginBottom: '6px' }}>
          <h1
            className="font-display text-[22px]"
            style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
          >
            {detail.label}
          </h1>
          <StatusBadge status={detail.connection_status} />
        </div>
        <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
          {detail.source_key} · {detail.schedule}
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex gap-1"
        style={{
          borderBottom: '1px solid var(--color-line)',
          marginBottom: '20px',
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className="text-[13px]"
            style={{
              padding: '8px 14px',
              color: tab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
              borderBottom: `2px solid ${tab === t.key ? 'var(--color-accent)' : 'transparent'}`,
              marginBottom: '-1px',
              fontWeight: tab === t.key ? 500 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <ConnectorOverviewTab detail={detail} />}
      {tab === 'permissions' && (
        <ConnectorPermissionsTab detail={detail} onChanged={onChanged} />
      )}
      {tab === 'health' && <ConnectorHealthTab detail={detail} />}
    </div>
  );
}

function StatusBadge({ status }: { status: ConnectorDetail['connection_status'] }) {
  const colors: Record<typeof status, { bg: string; fg: string; label: string }> = {
    connected: { bg: '#DCFCE7', fg: '#15803D', label: 'Connected' },
    available: { bg: '#F4F4F5', fg: '#52525B', label: 'Available' },
    disabled: { bg: '#FEE2E2', fg: '#B91C1C', label: 'Disabled' },
  };
  const c = colors[status];
  return (
    <span
      className="text-[10px] font-medium uppercase tracking-wider"
      style={{
        background: c.bg,
        color: c.fg,
        padding: '3px 8px',
        borderRadius: '4px',
        letterSpacing: '0.06em',
      }}
    >
      {c.label}
    </span>
  );
}
