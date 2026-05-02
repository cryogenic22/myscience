import { MOVE_TYPE_META, type WarRoomRound } from '../../../api';
import ReactionCard from './ReactionCard';

interface Props {
  rounds: WarRoomRound[];
}

export default function RoundHistory({ rounds }: Props) {
  if (rounds.length === 0) {
    return (
      <div
        className="text-[12px] p-6"
        style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
      >
        No rounds yet — submit a move to model competitor reactions.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {[...rounds].reverse().map((rnd) => {
        const meta = MOVE_TYPE_META[rnd.move_type as keyof typeof MOVE_TYPE_META];
        const payloadEntries = Object.entries(rnd.move_payload || {}).filter(([, v]) => v);
        return (
          <div key={rnd.id}>
            {/* Player move header */}
            <div
              className="flex items-center gap-2 mb-3"
              style={{
                padding: '10px 14px',
                borderRadius: '6px',
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-line)',
              }}
            >
              <span
                className="text-[10px] uppercase font-medium px-2 py-0.5 rounded"
                style={{
                  background: 'var(--color-accent)',
                  color: 'white',
                  letterSpacing: '0.05em',
                }}
              >
                Round {rnd.round_number}
              </span>
              <span style={{ fontSize: '14px' }}>{meta?.icon ?? '▶'}</span>
              <span className="text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
                {meta?.label ?? rnd.move_type}
              </span>
              {payloadEntries.length > 0 && (
                <span className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
                  · {payloadEntries.map(([k, v]) => `${k}: ${String(v)}`).join(' · ')}
                </span>
              )}
            </div>

            {/* Reactions */}
            <div className="space-y-2 ml-3">
              {rnd.reactions.length === 0 ? (
                <div
                  className="text-[12px]"
                  style={{ color: 'var(--color-ink-4)', padding: '8px 14px' }}
                >
                  No reactions modeled — competitors had no actionable assets.
                </div>
              ) : (
                rnd.reactions.map((rxn, i) => (
                  <ReactionCard key={rxn.id ?? i} reaction={rxn} />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
