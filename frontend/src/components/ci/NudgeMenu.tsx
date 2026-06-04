/**
 * PB-203 / L13 — NudgeMenu: address a named agent with a bounded action.
 *
 * Renders a small "Nudge" affordance for one agent (Sentinel/Strategist/
 * Curator). Opening it lazily fetches the agent's intents from the registry
 * (so the menu can never offer an intent the backend rejects). Choosing an
 * intent that needs a target prompts for one — unless the parent supplies it
 * via `resolveTarget` (e.g. a scenario card already knows its scenario id).
 * Sending queues the nudge; the agent consumes it on its next pass, so the UI
 * confirms "Queued" rather than implying instant execution.
 */
import { useState } from 'react';
import { agentsApi } from '../../api';
import { AGENTS, type AgentId } from '../primitives/AgentGlyph';
import type { NudgeIntent } from '../../types/agents';

interface Props {
  agent: AgentId;
  /** Supply a target for an intent when the parent already knows it. Return
   *  undefined to fall back to the inline prompt. */
  resolveTarget?: (intent: NudgeIntent) => Record<string, unknown> | undefined;
  onNudged?: (intentKey: string) => void;
}

type Phase = 'idle' | 'menu' | 'target' | 'sending' | 'done' | 'error';

export default function NudgeMenu({ agent, resolveTarget, onNudged }: Props) {
  const meta = AGENTS[agent];
  const [phase, setPhase] = useState<Phase>('idle');
  const [intents, setIntents] = useState<NudgeIntent[]>([]);
  const [active, setActive] = useState<NudgeIntent | null>(null);
  const [targetValue, setTargetValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    setPhase('menu');
    setError(null);
    if (intents.length === 0) {
      try {
        const res = await agentsApi.intents(agent);
        setIntents(res.intents);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'failed to load intents');
        setPhase('error');
      }
    }
  };

  const close = () => {
    setPhase('idle');
    setActive(null);
    setTargetValue('');
    setError(null);
  };

  const send = async (intent: NudgeIntent, target?: Record<string, unknown>) => {
    setPhase('sending');
    setError(null);
    try {
      await agentsApi.nudge(agent, { intent: intent.key, target });
      setPhase('done');
      onNudged?.(intent.key);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'nudge failed');
      setPhase('error');
    }
  };

  const choose = (intent: NudgeIntent) => {
    setActive(intent);
    const supplied = resolveTarget?.(intent);
    if (supplied) {
      void send(intent, supplied);
    } else if (intent.requires_target) {
      setPhase('target');
    } else {
      void send(intent);
    }
  };

  const submitTarget = () => {
    if (!active) return;
    const key = `${active.target_kind ?? 'target'}_id`;
    void send(active, { [key]: targetValue.trim() });
  };

  return (
    <div data-testid="nudge-menu" data-agent={agent} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        data-testid="nudge-trigger"
        aria-label={`Nudge ${meta.name}`}
        onClick={() => (phase === 'idle' || phase === 'done' ? open() : close())}
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.05em',
          textTransform: 'uppercase', padding: '3px 9px',
          borderRadius: 'var(--radius-pill)', cursor: 'pointer',
          border: `1px solid rgba(${meta.rgb}, 0.45)`,
          background: `rgba(${meta.rgb}, 0.10)`, color: `rgb(${meta.rgb})`,
        }}
      >
        {phase === 'done' ? 'Queued ✓' : 'Nudge'}
      </button>

      {(phase === 'menu' || phase === 'target' || phase === 'error' || phase === 'sending') && (
        <div
          data-testid="nudge-popover"
          role="menu"
          style={{
            position: 'absolute', top: '100%', right: 0, marginTop: 6, zIndex: 20,
            minWidth: 240, padding: 'var(--space-3)',
            background: 'var(--color-surface)', border: '1px solid var(--color-line)',
            borderRadius: 'var(--radius-panel)', boxShadow: 'var(--shadow-md)',
          }}
        >
          {error && (
            <div data-testid="nudge-error" style={{ color: 'var(--color-red)', fontSize: 12, marginBottom: 6 }}>
              {error}
            </div>
          )}

          {phase === 'menu' && intents.map((it) => (
            <button
              key={it.key}
              data-testid={`nudge-intent-${it.key}`}
              role="menuitem"
              onClick={() => choose(it)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '7px 8px', borderRadius: 'var(--radius-sm, 6px)',
                border: 'none', background: 'transparent', cursor: 'pointer',
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-ink)' }}>{it.label}</span>
              <span style={{ display: 'block', fontSize: 11, color: 'var(--color-ink-3)', lineHeight: 1.35 }}>
                {it.description}
              </span>
            </button>
          ))}

          {phase === 'target' && active && (
            <div data-testid="nudge-target-form">
              <label style={{ display: 'block', fontSize: 11, color: 'var(--color-ink-3)', marginBottom: 4 }}>
                {active.label} — {active.target_kind} id
              </label>
              <input
                data-testid="nudge-target-input"
                value={targetValue}
                autoFocus
                onChange={(e) => setTargetValue(e.target.value)}
                placeholder={`${active.target_kind} id`}
                style={{
                  width: '100%', padding: '6px 8px', fontSize: 13,
                  border: '1px solid var(--color-line)', borderRadius: 'var(--radius-sm, 6px)',
                  marginBottom: 8, background: 'var(--color-bg)', color: 'var(--color-ink)',
                }}
              />
              <button
                data-testid="nudge-send"
                disabled={!targetValue.trim()}
                onClick={submitTarget}
                style={{
                  padding: '6px 14px', fontSize: 12, fontWeight: 500,
                  border: 'none', borderRadius: 'var(--radius-pill)',
                  cursor: targetValue.trim() ? 'pointer' : 'not-allowed',
                  background: 'var(--color-ink)', color: 'var(--color-bg)',
                  opacity: targetValue.trim() ? 1 : 0.5,
                }}
              >
                Queue nudge
              </button>
            </div>
          )}

          {phase === 'sending' && (
            <div data-testid="nudge-sending" style={{ fontSize: 12, color: 'var(--color-ink-3)' }}>
              Queuing…
            </div>
          )}
        </div>
      )}
    </div>
  );
}
