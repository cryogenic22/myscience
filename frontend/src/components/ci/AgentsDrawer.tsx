/**
 * L13 — Agents status drawer.
 *
 * The agent identity strip was pulled from the cockpit sidebar (it dominated
 * the nav); per that feedback the three agents resurface here, in a dismissible
 * status drawer that earns its own square footage instead of crowding
 * navigation. It surfaces the live activity feed (PB-202) AND makes each agent
 * addressable via NudgeMenu (PB-203) — Sentinel / Strategist / Curator.
 */
import { useState } from 'react';
import { useAgentActivity } from '../../hooks/useAgentActivity';
import AgentActivityFeed from '../primitives/AgentActivityFeed';

export default function AgentsDrawer() {
  const [open, setOpen] = useState(false);
  const { activities, loading } = useAgentActivity();

  return (
    <>
      <button
        data-testid="agents-drawer-trigger"
        aria-label="Open agents"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{
          position: 'fixed', right: 18, bottom: 18, zIndex: 40,
          display: 'inline-flex', alignItems: 'center', gap: 8,
          padding: '9px 15px', borderRadius: 'var(--radius-pill)',
          border: '1px solid var(--color-line)', cursor: 'pointer',
          background: 'var(--color-surface)', color: 'var(--color-ink-2)',
          boxShadow: 'var(--shadow-md)',
          fontFamily: 'var(--font-mono)', fontSize: 11,
          letterSpacing: '0.06em', textTransform: 'uppercase',
        }}
      >
        <span
          aria-hidden="true"
          style={{ width: 7, height: 7, borderRadius: 999, background: '#0a5a3f' }}
        />
        Agents
      </button>

      {open && (
        <>
          <div
            data-testid="agents-drawer-backdrop"
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 45, background: 'rgba(0,0,0,0.18)' }}
          />
          <aside
            data-testid="agents-drawer-panel"
            role="dialog"
            aria-label="Agents"
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 46,
              width: 'min(380px, 92vw)', padding: 'var(--space-5)',
              background: 'var(--color-surface)', borderLeft: '1px solid var(--color-line)',
              boxShadow: 'var(--shadow-lg)', overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--color-ink)' }}>
                  Agents
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-ink-4)' }}>
                  Sense · Frame · Learn — and nudge
                </div>
              </div>
              <button
                data-testid="agents-drawer-close"
                aria-label="Close agents"
                onClick={() => setOpen(false)}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 18, color: 'var(--color-ink-3)' }}
              >
                ×
              </button>
            </div>
            <AgentActivityFeed activities={activities} loading={loading} />
          </aside>
        </>
      )}
    </>
  );
}
