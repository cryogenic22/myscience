/**
 * PB-H13 — Autonomous war-game panel.
 *
 * Runs an N-round campaign where the agents play every team and narrate the
 * exchange; the human observes. Adversary reactions are DB-grounded
 * server-side (POST /war-rooms/{id}/run-autonomous). The transcript is
 * ephemeral — re-running replays the campaign.
 */
import { useState } from 'react';
import { warRoomApi, type AutoplayResult } from '../../../api';

const ROUNDS = 4;

export default function AutonomousPanel({ roomId }: { roomId: string }) {
  const [result, setResult] = useState<AutoplayResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await warRoomApi.runAutonomous(roomId, { rounds: ROUNDS });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="mz-text-sm" style={{ color: 'var(--color-ink-4)', margin: '0 0 14px', lineHeight: 1.6 }}>
        The agents play every team across {ROUNDS} rounds and narrate the exchange while you observe.
        Rival reactions are grounded in the knowledge graph — re-run to replay.
      </p>

      <button
        type="button"
        onClick={run}
        disabled={busy}
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em',
          textTransform: 'uppercase', padding: '9px 16px', borderRadius: 8,
          border: '1px solid var(--color-line)',
          background: busy ? 'var(--color-surface)' : 'var(--color-accent)',
          color: busy ? 'var(--color-ink-4)' : 'var(--color-bg)',
          cursor: busy ? 'default' : 'pointer',
        }}
      >
        {busy ? 'Playing…' : result ? 'Re-run autonomous play' : 'Run autonomous play'}
      </button>

      {error && (
        <div className="mz-text-sm" style={{ marginTop: 12, color: '#B91C1C' }}>{error}</div>
      )}

      {result && (
        <div data-autoplay-transcript style={{ marginTop: 18 }}>
          <div
            className="mz-text-xs uppercase font-medium"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em', marginBottom: 10 }}
          >
            Transcript · {result.summary.rounds_played} rounds · {result.summary.total_reactions} reactions
          </div>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {result.rounds.map((rd) => (
              <li
                key={rd.round}
                data-autoplay-round={rd.round}
                style={{
                  padding: '12px 14px', borderRadius: 8,
                  background: 'var(--color-surface)', border: '1px solid var(--color-line)',
                }}
              >
                <div className="mz-text-sm" style={{ color: 'var(--color-ink)', lineHeight: 1.5 }}>
                  {rd.narration}
                </div>
                <div className="mz-text-xs" style={{ color: 'var(--color-ink-4)', marginTop: 6 }}>
                  {rd.our_move.replace(/_/g, ' ')} · {rd.reactions.length} rival reaction{rd.reactions.length === 1 ? '' : 's'}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
