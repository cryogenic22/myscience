import { useState } from 'react';
import { Target } from 'lucide-react';
import { MOVE_TYPE_META, type WarRoomRound } from '../../../api';
import ReactionCard from './ReactionCard';
import PromoteToDecisionDialog from '../decisions/PromoteToDecisionDialog';

interface Props {
  rounds: WarRoomRound[];
  onPromoted?: () => void;
}

function isAuthed(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function RoundHistory({ rounds, onPromoted }: Props) {
  const [promoting, setPromoting] = useState<WarRoomRound | null>(null);
  const authed = isAuthed();
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
    <>
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
              {authed && (
                <button
                  type="button"
                  onClick={() => setPromoting(rnd)}
                  className="ml-auto text-[10px] inline-flex items-center gap-1 font-medium"
                  style={{
                    padding: '4px 9px',
                    borderRadius: '4px',
                    background: 'transparent',
                    color: 'var(--color-ink-3)',
                    border: '1px solid var(--color-line)',
                    cursor: 'pointer',
                  }}
                  title="Promote this round to a committed decision"
                >
                  <Target size={11} />
                  Promote to decision
                </button>
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
    {promoting && (
      <PromoteToDecisionDialog
        round={promoting}
        onClose={() => setPromoting(null)}
        onPromoted={() => {
          setPromoting(null);
          if (onPromoted) onPromoted();
        }}
      />
    )}
    </>
  );
}
