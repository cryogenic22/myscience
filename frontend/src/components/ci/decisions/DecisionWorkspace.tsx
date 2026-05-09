import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  decisionBriefsApi,
  type DecisionBrief,
  type DecisionBriefPatchBody,
  type DecisionBriefOptionInput,
  type BriefState,
} from '../../../api';
import BriefPanel from './BriefPanel';
import EvidencePanel from './EvidencePanel';
import SimulationPanel from './SimulationPanel';
import RecommendationPanel from './RecommendationPanel';
import ReasoningTraceDrawer from './ReasoningTraceDrawer';
import { nextForwardTransition } from './StateMachineChip';

/**
 * SPEC_030 §8.2 — 5-panel composite.
 *
 * Routes: /ci/decisions/:id (per App.tsx). Reads density from
 * localStorage.mz_density (default 'spacious') and wraps the tree in
 * data-density="..." per §8.8. Wires the keyboard contract from §6:
 * t (trace toggle), escape (close drawer), g e/s/r (focus panels),
 * cmd+enter (advance state when allowed).
 */

function isFixtureMode(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem('mz_fixture_mode') === 'true';
}

function getDensity(): 'spacious' | 'compact' {
  if (typeof window === 'undefined') return 'spacious';
  return window.localStorage.getItem('mz_density') === 'compact' ? 'compact' : 'spacious';
}

export default function DecisionWorkspace() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [brief, setBrief] = useState<DecisionBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [fixtureMode] = useState(isFixtureMode());

  const density = getDensity();

  const reload = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const r = await decisionBriefsApi.get(id);
      setBrief(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void reload(); }, [reload]);

  const onPatch = useCallback(
    async (patch: DecisionBriefPatchBody) => {
      if (!id) return;
      const updated = await decisionBriefsApi.patch(id, patch);
      setBrief(updated);
    },
    [id],
  );

  const onAddOption = useCallback(
    async (opt: DecisionBriefOptionInput) => {
      if (!id) return;
      await decisionBriefsApi.addOption(id, opt);
      await reload();
    },
    [id, reload],
  );

  const onRemoveOption = useCallback(
    async (optionId: string) => {
      if (!id) return;
      await decisionBriefsApi.removeOption(id, optionId);
      await reload();
    },
    [id, reload],
  );

  const onTransition = useCallback(
    async (toState: BriefState, reason?: string) => {
      if (!id) return;
      const updated = await decisionBriefsApi.transition(id, toState, reason);
      setBrief(updated);
    },
    [id],
  );

  // Keyboard contract: t (trace), escape (close), g e|s|r (focus), cmd+enter (advance state)
  useEffect(() => {
    let lastG = 0;
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;

      // Cmd / Ctrl + Enter — advance state forward (rank-aware) only.
      // Fixed in Stage 6 (#5): previous code picked transitions[0] which
      // for human_review was 'draft' — a backward transition.
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (brief && brief.state) {
          const target = nextForwardTransition(brief.state);
          if (target) void onTransition(target);
        }
        return;
      }

      if (e.key === 't') {
        e.preventDefault();
        setTraceOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setTraceOpen(false);
      } else if (e.key === 'g') {
        lastG = Date.now();
      } else if (Date.now() - lastG < 800) {
        // Within 800ms of pressing 'g' — interpret as g+letter shortcut
        const focusByTestId = (id: string) => {
          const el = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
          el?.focus();
        };
        if (e.key === 'e') {
          e.preventDefault();
          focusByTestId('panel-evidence');
        } else if (e.key === 's') {
          e.preventDefault();
          focusByTestId('panel-simulation');
        } else if (e.key === 'r') {
          e.preventDefault();
          focusByTestId('panel-recommendation');
        }
        lastG = 0;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [brief, onTransition]);

  if (loading && !brief) {
    return (
      <div
        aria-label="loading workspace"
        role="status"
        aria-live="polite"
        style={{
          padding: 'var(--space-panel-pad, 24px)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-panel-gap, 16px)',
        }}
      >
        <div
          style={{
            height: 220,
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-panel, 16px)',
            animation: 'skeleton-pulse 1.6s ease-in-out infinite',
          }}
        />
        <div style={{ display: 'flex', gap: 16 }}>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: 200,
                flex: 1,
                background: 'var(--color-surface-2)',
                borderRadius: 'var(--radius-panel, 16px)',
                animation: 'skeleton-pulse 1.6s ease-in-out infinite',
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (error || !brief) {
    return (
      <div
        style={{
          padding: 'var(--space-panel-pad, 24px)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          alignItems: 'flex-start',
        }}
      >
        <div style={{ fontSize: 13, color: 'var(--color-red, #C0392B)' }}>
          {error ?? 'Brief not found'}
        </div>
        <button
          type="button"
          onClick={() => navigate('/ci?tab=decisions')}
          className="btn btn-secondary btn-sm"
        >
          Back to briefs
        </button>
        {fixtureMode && (
          <div
            style={{
              padding: '8px 12px',
              background: 'var(--color-amber-soft, #FFFBEB)',
              color: 'var(--color-amber, #B45309)',
              borderRadius: 'var(--radius-card, 12px)',
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            Fixture mode — backend not connected
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      data-testid="decision-workspace-root"
      data-density={density}
      style={{
        padding: 'var(--space-panel-pad, 24px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-panel-gap, 16px)',
        position: 'relative',
      }}
    >
      {/* Top bar — back + state-aware shortcut hints */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          paddingBottom: 8,
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/ci?tab=decisions')}
          className="btn btn-ghost btn-sm"
          aria-label="back to briefs"
        >
          ← Back
        </button>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Brief {brief.brief_id.slice(0, 8)}
        </span>
        <button
          type="button"
          onClick={() => setTraceOpen((o) => !o)}
          className="btn btn-ghost btn-sm"
          style={{ marginLeft: 'auto' }}
          aria-label="toggle reasoning trace"
        >
          [t] trace
        </button>
      </header>

      <BriefPanel
        brief={brief}
        onPatch={onPatch}
        onAddOption={onAddOption}
        onRemoveOption={onRemoveOption}
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--space-panel-gap, 16px)',
        }}
      >
        <EvidencePanel brief={brief} />
        <SimulationPanel brief={brief} />
        <RecommendationPanel brief={brief} />
      </div>

      <ReasoningTraceDrawer
        brief={brief}
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
      />
    </div>
  );
}
