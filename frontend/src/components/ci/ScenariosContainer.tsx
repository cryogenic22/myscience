/**
 * UX04 — ScenariosContainer.
 *
 * Wires the (already-built, headless) ScenariosPage to the live engagement
 * scenario set (PB-H09 first-class probabilistic objects, derived server-side
 * from the dossier). Mirrors DossierContainer's state machine exactly.
 *
 * States:
 *   - loading       → fetching the scenario set
 *   - not-derived   → GET returned an empty list; offer to derive them from
 *                     the dossier (POST .../scenarios/assemble?narrative=true)
 *   - error         → load/derive failed
 *   - ready         → render ScenariosPage + a thin header (count + re-derive)
 *
 * The backend serialises to ScenariosPage's `Scenario` interface exactly, so
 * there is no reshaping — assembly is server-side, the UI is dumb.
 *
 * Fact drill-through reuses the shared ProvenancePanel (PB-UX03): a scenario's
 * trigger-evidence chip carries {factId, predicate}; we open the panel with the
 * cited evidence. (Full claim/sourceUrl resolution for a bare factId is a
 * follow-up — the chip already shows the real predicate it springs from.)
 */
import { useCallback, useEffect, useState } from 'react';
import { scenariosApi, type EngagementDTO } from '../../api';
import { ScenariosPage, type Scenario } from '../../pages/ScenariosPage';
import { type Fact } from '../../pages/EngagementDossierPage';
import ProvenancePanel from './ProvenancePanel';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
  /** Play a scenario in the War Room (workshop stage). */
  onPlayScenario?: (scenarioId: string) => void;
}

/** Find the cited evidence for a bare factId across the loaded scenarios. */
function findEvidence(scenarios: Scenario[], factId: string): { factId: string; predicate: string } | null {
  for (const s of scenarios) {
    const hit = s.trigger.evidence.find((e) => e.factId === factId);
    if (hit) return hit;
  }
  return null;
}

export default function ScenariosContainer({ engagement, onMarkComplete, onPlayScenario }: Props) {
  const eid = engagement.id;
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [deriving, setDeriving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [openFact, setOpenFact] = useState<Fact | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    scenariosApi.get(eid)
      .then((r) => { if (!cancelled) setScenarios(r.scenarios); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid]);

  useEffect(() => load(), [load]);

  const derive = async () => {
    setDeriving(true);
    setError(null);
    try {
      const r = await scenariosApi.assemble(eid, true);
      setScenarios(r.scenarios);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setDeriving(false);
    }
  };

  // factId → minimal Fact for the provenance panel (uses the real predicate).
  const onOpenFact = (factId: string) => {
    const ev = scenarios ? findEvidence(scenarios, factId) : null;
    setOpenFact({
      id: factId,
      claim: ev?.predicate ?? factId,
      factClass: 'inferred',
      sourceLabel: 'Cited as scenario trigger evidence',
    });
  };

  if (loading) {
    return (
      <Centered testId="scenarios-loading" tone="var(--color-ink-3)">
        Loading scenarios…
      </Centered>
    );
  }

  if (error) {
    return (
      <div data-testid="scenarios-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error}</ErrorLine>
        <button
          onClick={load}
          style={{
            marginTop: 12, padding: '8px 14px',
            fontFamily: 'var(--font-mono)', fontSize: 12,
            borderRadius: 'var(--radius-pill)', border: 'none', cursor: 'pointer',
            background: 'var(--color-surface-2)', color: 'var(--color-ink)',
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!scenarios || scenarios.length === 0) {
    return (
      <div
        data-testid="scenarios-empty"
        style={{
          padding: 'var(--space-7)',
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)',
          boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)',
          maxWidth: 640,
        }}
      >
        <SectionKicker>Scenarios · not yet derived</SectionKicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          Derive event-triggered scenarios for {engagement.name}
        </p>
        <p style={{ margin: '0 0 var(--space-5)', fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          Builds probabilistic futures for{' '}
          <strong style={{ color: 'var(--color-ink-2)' }}>{engagement.asset}</strong>{' '}
          from the latest dossier — each scenario a named trigger event with the
          facts that justify it, a structural prior, and team-move / decision
          scaffolding to play in the War Room. Closes the spine:
          fact → insight → <strong style={{ color: 'var(--color-ink-2)' }}>scenario</strong> → decision.
        </p>
        {error && <ErrorLine>{error}</ErrorLine>}
        <button
          data-testid="scenarios-derive"
          onClick={derive}
          disabled={deriving}
          style={{
            padding: '11px 20px',
            fontSize: 14, fontWeight: 500,
            borderRadius: 'var(--radius-pill)',
            border: 'none',
            cursor: deriving ? 'wait' : 'pointer',
            background: 'var(--color-ink)',
            color: 'var(--color-bg)',
            opacity: deriving ? 0.6 : 1,
          }}
        >
          {deriving ? 'Deriving…' : 'Derive scenarios'}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="scenarios-ready">
      {/* Thin header: count + re-derive. */}
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 'var(--space-4)', flexWrap: 'wrap',
          padding: 'var(--space-3) var(--space-4)',
          marginBottom: 'var(--space-4)',
          background: 'var(--color-surface-2)',
          borderRadius: 'var(--radius-pill)',
        }}
      >
        <div style={{ display: 'flex', gap: 'var(--space-5)', flexWrap: 'wrap', alignItems: 'baseline' }}>
          <KbStat label="Scenarios" value={String(scenarios.length)} />
          <KbStat
            label="Recommended"
            value={String(scenarios.filter((s) => s.decisionOutput).length)}
          />
          <KbStat
            label="Blocked"
            value={String(scenarios.filter((s) => (s.blockedByGaps?.length ?? 0) > 0).length)}
          />
        </div>
        <button
          data-testid="scenarios-rederive"
          onClick={derive}
          disabled={deriving}
          style={{
            padding: '7px 14px',
            fontFamily: 'var(--font-mono)', fontSize: 11,
            letterSpacing: '0.04em', textTransform: 'uppercase',
            borderRadius: 'var(--radius-pill)', border: 'none',
            cursor: deriving ? 'wait' : 'pointer',
            background: 'var(--color-surface-3, var(--color-surface))',
            color: 'var(--color-ink-2)',
            opacity: deriving ? 0.6 : 1,
          }}
        >
          {deriving ? 'Re-deriving…' : 'Re-derive'}
        </button>
      </div>

      <ScenariosPage
        scope={{ engagementName: engagement.name, focalAsset: engagement.asset }}
        scenarios={scenarios}
        activeScenarioId={activeId}
        onSelectScenario={setActiveId}
        onPlayScenario={(id) => onPlayScenario?.(id)}
        onOpenFact={onOpenFact}
        onMarkComplete={() => onMarkComplete?.()}
      />

      {/* PB-UX03: click trigger evidence → its provenance. */}
      <ProvenancePanel fact={openFact} onClose={() => setOpenFact(null)} />
    </div>
  );
}

// ── small atoms (mirror DossierContainer) ──────────────────────────

function Centered({ children, testId, tone }: { children: React.ReactNode; testId: string; tone: string }) {
  return (
    <div
      data-testid={testId}
      style={{ padding: 'var(--space-7)', color: tone, fontFamily: 'var(--font-mono)', fontSize: 12 }}
    >
      {children}
    </div>
  );
}

function SectionKicker({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
      textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 12,
    }}>
      {children}
    </div>
  );
}

function ErrorLine({ children }: { children: React.ReactNode }) {
  return (
    <p style={{
      margin: '0 0 4px', color: 'var(--color-red)',
      fontFamily: 'var(--font-mono)', fontSize: 13,
    }}>
      {children}
    </p>
  );
}

function KbStat({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'baseline' }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em',
        textTransform: 'uppercase', color: 'var(--color-ink-4)',
      }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>{value}</span>
    </span>
  );
}
