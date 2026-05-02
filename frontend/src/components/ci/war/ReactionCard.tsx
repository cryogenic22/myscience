import { REACTION_TYPE_META, type WarRoomReaction } from '../../../api';
import ScoreBars from './ScoreBars';

interface Props {
  reaction: WarRoomReaction;
}

const CONFIDENCE_DOT: Record<string, string> = {
  high: '#22C55E',
  medium: '#F59E0B',
  low: '#A1A1AA',
};

export default function ReactionCard({ reaction }: Props) {
  const meta = REACTION_TYPE_META[reaction.reaction_type];
  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${meta?.color ?? '#71717A'}`,
        borderRadius: '6px',
        padding: '14px 16px',
        background: 'var(--color-surface)',
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="text-[13px] font-medium"
              style={{ color: 'var(--color-ink)' }}
            >
              {reaction.competitor_company_name}
            </span>
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '2px 7px',
                borderRadius: '4px',
                background: meta?.color + '22',
                color: meta?.color,
                letterSpacing: '0.05em',
              }}
            >
              {meta?.label ?? reaction.reaction_type}
            </span>
          </div>
          {reaction.headline && (
            <div
              className="text-[12px] mt-1"
              style={{ color: 'var(--color-ink-2)' }}
            >
              {reaction.headline}
            </div>
          )}
        </div>
        {reaction.confidence && (
          <div className="flex items-center gap-1 shrink-0">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: CONFIDENCE_DOT[reaction.confidence] }}
            />
            <span className="text-[10px] uppercase" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}>
              {reaction.confidence}
            </span>
          </div>
        )}
      </div>

      {reaction.specific_action && (
        <div
          className="text-[12px] mb-2"
          style={{ color: 'var(--color-ink-3)', fontStyle: 'italic' }}
        >
          → {reaction.specific_action}
        </div>
      )}

      <div style={{ marginTop: '12px', marginBottom: '12px' }}>
        <ScoreBars scores={reaction.scores} />
      </div>

      {reaction.rationale && (
        <div
          className="text-[12px] leading-relaxed"
          style={{ color: 'var(--color-ink-3)' }}
        >
          {reaction.rationale}
        </div>
      )}

      {reaction.evidence_basis.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {reaction.evidence_basis.map((ev, i) => (
            <span
              key={i}
              className="text-[10px] font-mono"
              style={{
                padding: '2px 6px',
                borderRadius: '3px',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-4)',
              }}
            >
              {ev.length > 24 ? ev.slice(0, 24) + '…' : ev}
            </span>
          ))}
        </div>
      )}

      {reaction.asset_leveraged?.name && reaction.asset_leveraged.name !== 'n/a' && (
        <div
          className="mt-2 text-[10px] uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
        >
          Asset: <span style={{ color: 'var(--color-ink-3)' }}>{reaction.asset_leveraged.name}</span>
        </div>
      )}
    </div>
  );
}
