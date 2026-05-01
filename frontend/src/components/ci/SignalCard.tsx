import type { Signal } from '../../api';
import ConfidenceBadge from './ConfidenceBadge';
import ImpactBadge from './ImpactBadge';

interface Props {
  signal: Signal;
  selected: boolean;
  onSelect: () => void;
}

export default function SignalCard({ signal, selected, onSelect }: Props) {
  const dateStr = signal.created_at
    ? new Date(signal.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : '';
  const isSupersedence = !!signal.superseded_by;

  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full text-left transition-colors"
      style={{
        padding: '12px 14px',
        background: selected ? 'var(--color-surface)' : 'transparent',
        borderLeft: `2px solid ${selected ? 'var(--color-accent)' : 'transparent'}`,
        borderBottom: '1px solid var(--color-line)',
      }}
    >
      {isSupersedence && (
        <div
          className="text-[10px] uppercase mb-1"
          style={{ color: '#A16207', letterSpacing: '0.06em', fontWeight: 500 }}
        >
          ⤴ Updates earlier signal
        </div>
      )}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div
            className="text-[13px] font-medium leading-snug"
            style={{ color: 'var(--color-ink)' }}
          >
            {signal.headline}
          </div>
          {signal.primary_entity_name && (
            <div
              className="text-[11px] mt-1 truncate"
              style={{ color: 'var(--color-ink-4)' }}
            >
              {signal.primary_entity_name}
              {signal.kbq_tags.length > 0 && (
                <>
                  <span> · </span>
                  <span style={{ color: 'var(--color-ink-3)' }}>
                    {signal.kbq_tags.slice(0, 2).join(', ')}
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2">
          <ConfidenceBadge tier={signal.confidence_tier} />
          <ImpactBadge tier={signal.impact_tier} />
        </div>
        <span className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          {dateStr}
        </span>
      </div>
    </button>
  );
}
