/**
 * DF-1/DF-2 — ForgeRoundView: the playable SME elicitation round.
 *
 * One play, end to end: fetch a grounded round (a real drug-vs-drug compare),
 * rank the analytical dimensions that matter, submit, and see the quality-gated
 * score + whether the top pick was PROMOTED (consensus → applied to the
 * playbook) or FLAGGED (a proposal awaiting corroboration). It is a game — a
 * 60-second framing, a score, a streak — but every reward is gated on the
 * answer actually validating, so volume never beats correctness.
 *
 * Constrained by construction: the SME picks/ranks FROM the round's option set
 * (each option carries the routable predicate(s) it forges), so an answer is
 * always plannable — never free text the planner can't execute.
 *
 * House style: design-token CSS variables + inline styles, no dynamic Tailwind
 * class names (Tailwind v4 / Railway scanner). Reuses FactClassGlyph is N/A
 * here (no facts in a round) — the pack panel renders the grown playbook.
 */
import { useEffect, useState } from 'react';
import { ArrowUp, ArrowDown, Check, Trophy, Flag, RotateCw } from 'lucide-react';
import {
  forgeApi,
  type ForgeRound,
  type ForgeAnswerResult,
  type ForgeSessionSummary,
} from '../../api';

interface Props {
  sessionId: string;
  playbookId?: string;
  /** Notify the parent when an answer lands so the pack panel can refresh. */
  onAnswered?: (result: ForgeAnswerResult) => void;
}

type Phase = 'loading' | 'playing' | 'submitting' | 'result' | 'error';

export default function ForgeRoundView({ sessionId, playbookId, onAnswered }: Props) {
  const [round, setRound] = useState<ForgeRound | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<string | null>(null);
  // The SME's ranking: an ordered list of option keys (most important first).
  const [ranking, setRanking] = useState<string[]>([]);
  const [result, setResult] = useState<ForgeAnswerResult | null>(null);
  const [session, setSession] = useState<ForgeSessionSummary | null>(null);

  const loadSession = async () => {
    try {
      setSession(await forgeApi.session(sessionId));
    } catch {
      /* session summary is best-effort — never blocks play */
    }
  };

  const newRound = async () => {
    setPhase('loading');
    setError(null);
    setResult(null);
    setRanking([]);
    try {
      const r = await forgeApi.createRound(sessionId, { playbookId });
      setRound(r);
      setPhase('playing');
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setPhase('error');
    }
  };

  useEffect(() => {
    newRound();
    loadSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, playbookId]);

  const options = round?.payload?.options ?? [];
  const selectedSet = new Set(ranking);

  const toggle = (key: string) => {
    setRanking((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const move = (key: string, dir: -1 | 1) => {
    setRanking((prev) => {
      const i = prev.indexOf(key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  };

  const submit = async () => {
    if (!round || ranking.length === 0) return;
    setPhase('submitting');
    try {
      const res = await forgeApi.submitAnswer(round.id, { selected: ranking, ranking });
      setResult(res);
      setPhase('result');
      onAnswered?.(res);
      loadSession();
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setPhase('error');
    }
  };

  // ── chrome: score / streak header (the game framing) ──
  const header = (
    <div
      data-testid="forge-scoreboard"
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12, marginBottom: 'var(--space-4)',
      }}
    >
      <div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 4,
        }}>
          Domain Forge · what matters?
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--color-ink-3)' }}>
          ~60 seconds. Rank the dimensions that matter — your top pick is forged into the answer playbook.
        </p>
      </div>
      <div style={{ display: 'flex', gap: 18 }}>
        <Stat label="Score" value={session?.score ?? 0} testId="forge-stat-score" />
        <Stat label="Rounds" value={session?.rounds_answered ?? 0} testId="forge-stat-rounds" />
        <Stat label="Promoted" value={session?.promoted ?? 0} testId="forge-stat-promoted" />
      </div>
    </div>
  );

  if (phase === 'error') {
    return (
      <div data-testid="forge-round">
        {header}
        <div data-testid="forge-error" style={{
          color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13,
          padding: 'var(--space-4)', background: 'var(--color-surface-2)', borderRadius: 10,
        }}>
          {error}
        </div>
        <button data-testid="forge-retry" onClick={newRound} style={primaryBtn(false)}>
          <RotateCw size={14} /> Try another round
        </button>
      </div>
    );
  }

  if (phase === 'loading' || !round) {
    return (
      <div data-testid="forge-round">
        {header}
        <div data-testid="forge-loading" style={{
          fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)',
          padding: 'var(--space-5)',
        }}>
          Dealing a round from the knowledge base…
        </div>
      </div>
    );
  }

  // ── the result card (score + promoted/flagged) ──
  if (phase === 'result' && result) {
    return (
      <div data-testid="forge-round">
        {header}
        <ResultCard result={result} onNext={newRound} />
      </div>
    );
  }

  // ── the playing card (prompt + rank control) ──
  const orderedUnpicked = options.filter((o) => !selectedSet.has(o.key));

  return (
    <div data-testid="forge-round">
      {header}

      <div
        data-testid="forge-prompt"
        style={{
          fontFamily: 'var(--font-display)', fontSize: 22, lineHeight: 1.3,
          color: 'var(--color-ink)', marginBottom: 'var(--space-4)', maxWidth: 720,
        }}
      >
        {round.prompt}
      </div>

      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: 'var(--color-ink-4)', marginBottom: 8,
      }}>
        Your ranking — most important first
      </div>

      {/* The ranked picks (ordered, reorderable) */}
      {ranking.length > 0 ? (
        <ol data-testid="forge-ranking" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {ranking.map((key, i) => {
            const opt = options.find((o) => o.key === key);
            if (!opt) return null;
            return (
              <li
                key={key}
                data-testid={`forge-ranked-${key}`}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px', borderRadius: 10,
                  background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
                }}
              >
                <span style={{
                  width: 22, height: 22, flexShrink: 0, borderRadius: '50%',
                  background: 'var(--color-accent)', color: 'var(--color-surface)',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700,
                }}>{i + 1}</span>
                <span style={{ flex: 1, fontSize: 13.5, color: 'var(--color-ink)' }}>{opt.label}</span>
                <button aria-label={`Move ${opt.label} up`} data-testid={`forge-up-${key}`}
                  onClick={() => move(key, -1)} disabled={i === 0} style={iconBtn(i === 0)}>
                  <ArrowUp size={14} />
                </button>
                <button aria-label={`Move ${opt.label} down`} data-testid={`forge-down-${key}`}
                  onClick={() => move(key, 1)} disabled={i === ranking.length - 1} style={iconBtn(i === ranking.length - 1)}>
                  <ArrowDown size={14} />
                </button>
                <button aria-label={`Remove ${opt.label}`} data-testid={`forge-remove-${key}`}
                  onClick={() => toggle(key)} style={{ ...iconBtn(false), color: 'var(--color-ink-4)' }}>
                  ×
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p style={{ fontSize: 12.5, color: 'var(--color-ink-4)', fontStyle: 'italic', margin: '4px 0 0' }}>
          Pick at least one dimension below to build your ranking.
        </p>
      )}

      {/* The remaining option pool */}
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em',
        textTransform: 'uppercase', color: 'var(--color-ink-4)', margin: '16px 0 8px',
      }}>
        Candidate dimensions
      </div>
      <div data-testid="forge-options" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {orderedUnpicked.map((o) => (
          <button
            key={o.key}
            data-testid={`forge-option-${o.key}`}
            onClick={() => toggle(o.key)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 13px', fontSize: 13, fontFamily: 'var(--font-body)',
              borderRadius: 'var(--radius-pill)', cursor: 'pointer',
              border: '1px solid var(--color-line)', background: 'var(--color-surface)',
              color: 'var(--color-ink-2)',
            }}
          >
            <span style={{ color: 'var(--color-ink-4)' }}>+</span> {o.label}
          </button>
        ))}
        {orderedUnpicked.length === 0 && (
          <span style={{ fontSize: 12.5, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
            All dimensions ranked.
          </span>
        )}
      </div>

      <button
        data-testid="forge-submit"
        onClick={submit}
        disabled={ranking.length === 0 || phase === 'submitting'}
        style={primaryBtn(ranking.length === 0 || phase === 'submitting')}
      >
        <Check size={15} /> {phase === 'submitting' ? 'Forging…' : 'Forge this dimension'}
      </button>
    </div>
  );
}

function Stat({ label, value, testId }: { label: string; value: number; testId: string }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div data-testid={testId} style={{
        fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 600,
        color: 'var(--color-ink)', lineHeight: 1,
      }}>{value}</div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: 'var(--color-ink-4)', marginTop: 3,
      }}>{label}</div>
    </div>
  );
}

function ResultCard({ result, onNext }: { result: ForgeAnswerResult; onNext: () => void }) {
  const promoted = result.consensus.state === 'promoted';
  const valid = result.validation.valid;
  const accent = !valid
    ? 'var(--color-red)'
    : promoted
      ? 'var(--color-green)'
      : 'var(--color-amber)';

  return (
    <div
      data-testid="forge-result"
      style={{
        border: `1px solid ${accent}`, borderRadius: 14, overflow: 'hidden',
        background: 'var(--color-surface)', maxWidth: 640,
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '16px 18px',
        background: 'var(--color-surface-2)',
      }}>
        <span style={{
          width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: accent, color: 'var(--color-surface)',
        }}>
          {promoted ? <Trophy size={20} /> : <Flag size={20} />}
        </span>
        <div style={{ flex: 1 }}>
          <div data-testid="forge-result-state" style={{
            fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 600,
            color: 'var(--color-ink)',
          }}>
            {!valid ? 'Not validated' : promoted ? 'Promoted to the playbook' : 'Flagged as a proposal'}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--color-ink-3)', marginTop: 2 }}>
            You forged <strong>{result.dimension.label}</strong>
            {promoted && result.playbook_version != null && (
              <> — now live in playbook <strong>v{result.playbook_version}</strong></>
            )}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div data-testid="forge-points" style={{
            fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 700, color: accent, lineHeight: 1,
          }}>
            +{result.score.points}
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
            textTransform: 'uppercase', color: 'var(--color-ink-4)', marginTop: 2,
          }}>points</div>
        </div>
      </div>

      <div style={{ padding: '14px 18px' }}>
        <p data-testid="forge-result-reason" style={{ margin: 0, fontSize: 13, color: 'var(--color-ink-2)' }}>
          {result.score.reason}
        </p>

        {/* Consensus progress — the "you made the system smarter" payoff */}
        <div style={{ marginTop: 12 }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)',
            fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--color-ink-4)', marginBottom: 5,
          }}>
            <span>SME consensus</span>
            <span data-testid="forge-consensus-count">
              {result.consensus.agree_count} / {result.consensus.threshold}
            </span>
          </div>
          <div style={{ height: 7, borderRadius: 99, background: 'var(--color-surface-3)', overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${Math.min(100, (result.consensus.agree_count / Math.max(1, result.consensus.threshold)) * 100)}%`,
              background: accent, transition: 'width 240ms ease',
            }} />
          </div>
        </div>

        {!valid && result.validation.errors.length > 0 && (
          <ul data-testid="forge-validation-errors" style={{
            margin: '12px 0 0', paddingLeft: 18, fontSize: 12, color: 'var(--color-red)',
          }}>
            {result.validation.errors.map((err, i) => <li key={i}>{err}</li>)}
          </ul>
        )}
      </div>

      <div style={{ padding: '0 18px 16px' }}>
        <button data-testid="forge-next" onClick={onNext} style={primaryBtn(false)}>
          <RotateCw size={14} /> Next round
        </button>
      </div>
    </div>
  );
}

function primaryBtn(disabled: boolean): React.CSSProperties {
  return {
    marginTop: 'var(--space-4)', display: 'inline-flex', alignItems: 'center', gap: 7,
    padding: '10px 18px', fontSize: 13.5, fontWeight: 500,
    borderRadius: 'var(--radius-pill)', border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    background: 'var(--color-ink)', color: 'var(--color-bg)', opacity: disabled ? 0.5 : 1,
  };
}

function iconBtn(disabled: boolean): React.CSSProperties {
  return {
    width: 26, height: 26, flexShrink: 0, borderRadius: 7, border: '1px solid var(--color-line)',
    background: 'var(--color-surface)', color: 'var(--color-ink-3)',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.4 : 1, fontSize: 14,
  };
}
