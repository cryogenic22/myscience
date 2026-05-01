import type { ConnectorSummary } from '../../api';
import ConnectorListItem from './ConnectorListItem';

interface Props {
  connectors: ConnectorSummary[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export default function ConnectorList({ connectors, selectedKey, onSelect }: Props) {
  const connected = connectors.filter((c) => c.connection_status === 'connected');
  const available = connectors.filter((c) => c.connection_status !== 'connected');

  return (
    <div
      className="overflow-y-auto"
      style={{
        width: '280px',
        borderRight: '1px solid var(--color-line)',
        padding: '16px 12px',
        background: 'var(--color-surface-2)',
      }}
    >
      <Section title={`Connected (${connected.length})`}>
        {connected.map((c) => (
          <ConnectorListItem
            key={c.source_key}
            connector={c}
            selected={c.source_key === selectedKey}
            onSelect={() => onSelect(c.source_key)}
          />
        ))}
      </Section>

      <Section title={`Available (${available.length})`}>
        {available.map((c) => (
          <ConnectorListItem
            key={c.source_key}
            connector={c}
            selected={c.source_key === selectedKey}
            onSelect={() => onSelect(c.source_key)}
          />
        ))}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '20px' }}>
      <div
        className="text-[10px] uppercase tracking-wider font-medium"
        style={{
          color: 'var(--color-ink-4)',
          padding: '0 12px 8px',
          letterSpacing: '0.06em',
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}
