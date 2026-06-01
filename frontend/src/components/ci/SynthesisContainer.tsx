/**
 * UX06 — SynthesisContainer.
 *
 * Wires the (already-built, headless) SynthesisPage to the live engagement
 * synthesis set (PB-UX06: typed insights derived from the dossier, each citing
 * the facts it springs from + the rejected-candidate audit trail). Mirrors
 * ScenariosContainer's state machine.
 *
 * States:
 *   - loading       → fetching the synthesis set
 *   - not-derived   → no insights AND no rejected yet; offer to derive them
 *   - error         → load/derive failed
 *   - ready         → render SynthesisPage + a thin header (counts + pass-rate)
 *
 * Backend serialises to SynthesisPage's `Insight`/`RejectedInsight` shapes
 * exactly — no reshaping. Fact drill-through reuses the shared ProvenancePanel
 * (UX03): an insight's citation carries {factId, predicate, contribution}; we
 * open the panel with the cited evidence.
 */
import { useCallback, useEffect, useState } from 'react';
import { synthesisApi, type SynthesisResponse, type EngagementDTO } from '../../api';
import { SynthesisPage } from '../../pages/SynthesisPage';
import { type Fact } from '../../pages/EngagementDossierPage';
import ProvenancePanel from './ProvenancePanel';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

/** Find a citation for a bare factId across the loaded insights + rejected. */
function findCitation(set: SynthesisResponse | null, factId: string): { predicate: string; contribution: string } | null {
  if (!set) return null;
  for (const i of set.insights) {
    const hit = i.derivedFrom.find((c) => c.factId === factId);
    if (hit) return hit;
  }
  for (const r of set.rejectedInsights) {
    const hit = (r.derivedFrom ?? []).find((c) => c.factId === factId);
    if (hit) return hit;
  }
  return null;
}

export default function SynthesisContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const [data, setData] = useState<SynthesisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [deriving, setDeriving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openFact, setOpenFact] = useState<Fact | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    synthesisApi.get(eid)
      .then((r) => { if (!cancelled) setData(r); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid]);

  useEffect(() => load(), [load]);

  const derive = async () => {
    setDeriving(true);
    setError(null);
    try {
      setData(await synthesisApi.assemble(eid));
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setDeriving(false);
    }
  };

  const onOpenFact = (factId: string) => {
    const c = findCitation(data, factId);
    setOpenFact({
      id: factId,
      claim: c?.contribution || c?.predicate || factId,
      factClass: 'inferred',
      sourceLabel: 'Cited as insight evidence',
    });
  };

  if (loading) {
    return (
      <Centered testId="synthesis-loading" tone="var(--color-ink-3)">
        Loading synthesis…
      </Centered>
    );
  }

  if (error) {
    return (
      <div data-testid="synthesis-error" style={{ padding: 'var(--space-7)' }}>
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

  const empty = !data || (data.insights.length === 0 && data.rejectedInsights.length === 0);
  if (empty) {
    return (
      <div
        data-testid="synthesis-empty"
        style={{
          padding: 'var(--space-7)',
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)',
          boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)',
          maxWidth: 640,
        }}
      >
        <SectionKicker>Synthesis · not yet derived</SectionKicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          Synthesise insights for {engagement.name}
        </p>
        <p style={{ margin: '0 0 var(--space-5)', fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          Distils the {engagement.asset} dossier into typed, strategically-framed
          insights — each tracing back to the facts that justify it (the
          anti-hallucination contract). Candidates that fail the synthesis test
          are logged as the audit trail. Closes the spine:
          fact → <strong style={{ color: 'var(--color-ink-2)' }}>insight</strong> → scenario.
        </p>
        {error && <ErrorLine>{error}</ErrorLine>}
        <button
          data-testid="synthesis-derive"
          onClick={derive}
          disabled={deriving}
          style={{
            padding: '11px 20px', fontSize: 14, fontWeight: 500,
            borderRadius: 'var(--radius-pill)', border: 'none',
            cursor: deriving ? 'wait' : 'pointer',
            background: 'var(--color-ink)', color: 'var(--color-bg)',
            opacity: deriving ? 0.6 : 1,
          }}
        >
          {deriving ? 'Synthesising…' : 'Synthesise insights'}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="synthesis-ready">
      {/* Thin header: counts + pass-rate + re-derive. */}
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
          <KbStat label="Insights" value={String(data!.insights.length)} />
          <KbStat label="Rejected" value={String(data!.rejectedInsights.length)} />
          <KbStat label="Pass-rate" value={`${data!.passRate}%`} />
        </div>
        <button
          data-testid="synthesis-rederive"
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
          {deriving ? 'Re-synthesising…' : 'Re-synthesise'}
        </button>
      </div>

      <SynthesisPage
        scope={{ engagementName: engagement.name, focalAsset: engagement.asset }}
        insights={data!.insights}
        rejectedInsights={data!.rejectedInsights}
        onOpenFact={onOpenFact}
        onMarkComplete={() => onMarkComplete?.()}
      />

      {/* PB-UX03: click a citation → its provenance. */}
      <ProvenancePanel fact={openFact} onClose={() => setOpenFact(null)} />
    </div>
  );
}

// ── small atoms (mirror ScenariosContainer) ────────────────────────

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
