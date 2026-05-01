import type { ConnectorSummary } from '../../api';

interface Props {
  connector: ConnectorSummary;
  selected: boolean;
  onSelect: () => void;
}

const STATUS_DOT: Record<ConnectorSummary['connection_status'], string> = {
  connected: '#22C55E',
  available: '#A1A1AA',
  disabled: '#EF4444',
};

const STATUS_LABEL: Record<ConnectorSummary['connection_status'], string> = {
  connected: 'Connected',
  available: 'Available',
  disabled: 'Disabled',
};

export default function ConnectorListItem({ connector, selected, onSelect }: Props) {
  const lastRun = connector.last_run?.completed_at
    ? new Date(connector.last_run.completed_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
      })
    : '—';

  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full text-left transition-colors"
      style={{
        padding: '10px 12px',
        background: selected ? 'var(--color-surface)' : 'transparent',
        borderLeft: `2px solid ${selected ? 'var(--color-accent)' : 'transparent'}`,
        borderRadius: '6px',
        marginBottom: '2px',
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full shrink-0"
          style={{ background: STATUS_DOT[connector.connection_status] }}
        />
        <span
          className="text-[13px] font-medium truncate"
          style={{ color: 'var(--color-ink)' }}
        >
          {connector.label}
        </span>
      </div>
      <div
        className="flex items-center gap-2 mt-1 text-[11px]"
        style={{ color: 'var(--color-ink-4)', paddingLeft: '16px' }}
      >
        <span>{STATUS_LABEL[connector.connection_status]}</span>
        <span>·</span>
        <span>{lastRun}</span>
      </div>
    </button>
  );
}
