import { useState } from 'react';
import { Sparkles, Check } from 'lucide-react';
import { warRoomApi, MOVE_TYPE_META, type MoveSuggestion, type MoveType } from '../../../api';

interface Props {
  roomId: string;
  signalContext?: Record<string, unknown>;
  onPick: (move_type: MoveType, payload: Record<string, string>) => void;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function MoveSuggestions({ roomId, signalContext, onPick }: Props) {
  const authed = hasToken();
  const [suggestions, setSuggestions] = useState<MoveSuggestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickedIdx, setPickedIdx] = useState<number | null>(null);

  const generate = async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    setPickedIdx(null);
    try {
      const r = await warRoomApi.suggestMoves(roomId, {
        n: 3,
        signal_context: signalContext,
      });
      setSuggestions(r.suggestions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderRadius: '8px',
        padding: '14px 16px',
        background: 'var(--color-surface-2)',
        marginBottom: '12px',
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Sparkles size={14} style={{ color: 'var(--color-accent)' }} />
          <span
            className="text-[12px] font-medium"
            style={{ color: 'var(--color-ink)' }}
          >
            Let the system suggest moves
          </span>
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '1px 7px',
              borderRadius: '4px',
              background: 'var(--color-accent)',
              color: 'white',
              letterSpacing: '0.05em',
            }}
            title="Phase A.5 — system proposes, you decide. Still AI-assisted."
          >
            A.5
          </span>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={!authed || loading}
          className="text-[11px] font-medium"
          style={{
            padding: '4px 12px',
            borderRadius: '6px',
            background: authed && !loading ? 'var(--color-accent)' : 'var(--color-surface)',
            color: authed && !loading ? 'white' : 'var(--color-ink-4)',
            border: 'none',
            cursor: authed && !loading ? 'pointer' : 'not-allowed',
          }}
        >
          {loading ? 'Thinking…' : suggestions ? 'Re-run' : 'Suggest 3 moves'}
        </button>
      </div>

      {!authed && (
        <div className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          Log in (viewer or above) to generate move suggestions.
        </div>
      )}

      {error && (
        <div
          className="text-[11px] mt-2"
          style={{ color: '#B91C1C' }}
        >
          {error}
        </div>
      )}

      {suggestions && suggestions.length === 0 && !loading && (
        <div
          className="text-[11px] mt-2"
          style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
        >
          The system found no actionable moves given the player's current
          dossier. Honest fallback.
        </div>
      )}

      {suggestions && suggestions.length > 0 && (
        <div className="grid grid-cols-1 gap-2 mt-3">
          {suggestions.map((s, i) => (
            <SuggestionCard
              key={i}
              suggestion={s}
              picked={pickedIdx === i}
              onPick={() => {
                setPickedIdx(i);
                onPick(s.move_type, s.move_payload);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SuggestionCard({
  suggestion, picked, onPick,
}: {
  suggestion: MoveSuggestion;
  picked: boolean;
  onPick: () => void;
}) {
  const meta = MOVE_TYPE_META[suggestion.move_type];
  const impactPct = Math.round(suggestion.expected_impact_score * 100);
  const confPct = Math.round(suggestion.confidence_score * 100);

  return (
    <button
      type="button"
      onClick={onPick}
      className="text-left w-full"
      style={{
        padding: '12px 14px',
        borderRadius: '6px',
        border: `1.5px solid ${picked ? 'var(--color-accent)' : 'var(--color-line)'}`,
        background: 'var(--color-surface)',
        cursor: 'pointer',
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ fontSize: '14px' }}>{meta.icon}</span>
        <span
          className="text-[13px] font-medium"
          style={{ color: 'var(--color-ink)' }}
        >
          {meta.label}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 7px',
              borderRadius: '4px',
              background: '#DCFCE7',
              color: '#15803D',
              letterSpacing: '0.05em',
            }}
            title="Predicted impact magnitude × probability"
          >
            Impact {impactPct}%
          </span>
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 7px',
              borderRadius: '4px',
              background: 'var(--color-surface-2)',
              color: 'var(--color-ink-3)',
              letterSpacing: '0.05em',
            }}
            title="System confidence in the recommendation"
          >
            Conf {confPct}%
          </span>
          {picked && (
            <Check size={14} style={{ color: 'var(--color-accent)' }} />
          )}
        </div>
      </div>

      <div
        className="text-[12px] leading-snug mb-2"
        style={{ color: 'var(--color-ink-2)' }}
      >
        {suggestion.rationale}
      </div>

      {Object.keys(suggestion.move_payload).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(suggestion.move_payload).map(([k, v]) => (
            <span
              key={k}
              className="text-[10px]"
              style={{
                padding: '2px 7px',
                borderRadius: '3px',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-3)',
              }}
            >
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {!suggestion.evidence_validated && suggestion.stripped_citations.length > 0 && (
        <div
          className="text-[10px] mt-2 inline-flex items-center gap-1"
          style={{
            padding: '2px 7px',
            borderRadius: '4px',
            background: '#FEF3C7',
            color: '#A16207',
          }}
          title={`Stripped: ${suggestion.stripped_citations.join(', ')}`}
        >
          ⚠ {suggestion.stripped_citations.length} citation{suggestion.stripped_citations.length === 1 ? '' : 's'} unverified
        </div>
      )}
    </button>
  );
}
