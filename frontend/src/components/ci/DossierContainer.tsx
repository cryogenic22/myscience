/**
 * KB3 — DossierContainer.
 *
 * Wires the (already-built) EngagementDossierPage to the live Dossier
 * Knowledge Base (KB2). Replaces the "coming soon" placeholder for the
 * dossier stage.
 *
 * States:
 *   - loading        → fetching the latest snapshot
 *   - not-assembled  → no snapshot yet; offer to assemble one from the
 *                       facts ledger (POST .../dossier/assemble)
 *   - error          → load/assemble failed
 *   - ready          → render the 8-domain dossier + a thin KB header
 *                       (version, coverage, re-assemble)
 *
 * The backend `domains` payload already matches EngagementDossierPage's
 * DomainView, so there's no reshaping — assembly is server-side.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  dossierKbApi,
  DossierNotAssembled,
  type DossierSnapshotDTO,
  type EngagementDTO,
} from '../../api';
import {
  EngagementDossierPage,
  type DomainView,
  type DossierDomain,
} from '../../pages/EngagementDossierPage';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

function toDomainViews(snapshot: DossierSnapshotDTO): DomainView[] {
  return snapshot.domains.map((d) => ({
    domain: d.domain as DossierDomain,
    priority: d.priority,
    state: d.state,
    facts: d.facts.map((f) => ({
      id: f.id,
      claim: f.claim,
      factClass: f.factClass,
      sourceLabel: f.sourceLabel,
    })),
  }));
}

export default function DossierContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const [snapshot, setSnapshot] = useState<DossierSnapshotDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAssembled, setNotAssembled] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotAssembled(false);
    dossierKbApi.get(eid)
      .then((s) => { if (!cancelled) setSnapshot(s); })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof DossierNotAssembled) setNotAssembled(true);
        else setError(String(e?.message ?? e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid]);

  useEffect(() => load(), [load]);

  const assemble = async () => {
    setAssembling(true);
    setError(null);
    try {
      const s = await dossierKbApi.assemble(eid);
      setSnapshot(s);
      setNotAssembled(false);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setAssembling(false);
    }
  };

  const jumpToDomain = (domain: DossierDomain) => {
    const el = document.getElementById(`dossier-domain-${domain}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (loading) {
    return (
      <Centered testId="dossier-loading" tone="var(--color-ink-3)">
        Loading dossier…
      </Centered>
    );
  }

  if (notAssembled) {
    return (
      <div
        data-testid="dossier-empty"
        style={{
          padding: 'var(--space-7)',
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)',
          boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)',
          maxWidth: 640,
        }}
      >
        <SectionKicker>Dossier · not yet assembled</SectionKicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          Build the dossier for {engagement.name}
        </p>
        <p style={{ margin: '0 0 var(--space-5)', fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          Assembles an 8-domain, evidence-grounded read of{' '}
          <strong style={{ color: 'var(--color-ink-2)' }}>{engagement.asset}</strong>{' '}
          from the facts ledger — every claim carries its source and class.
          Thin domains surface as gaps to drive what the sense layer collects next.
        </p>
        {error && <ErrorLine>{error}</ErrorLine>}
        <button
          data-testid="dossier-assemble"
          onClick={assemble}
          disabled={assembling}
          style={{
            padding: '11px 20px',
            fontSize: 14, fontWeight: 500,
            borderRadius: 'var(--radius-pill)',
            border: 'none',
            cursor: assembling ? 'wait' : 'pointer',
            background: 'var(--color-ink)',
            color: 'var(--color-bg)',
            opacity: assembling ? 0.6 : 1,
          }}
        >
          {assembling ? 'Assembling…' : 'Assemble dossier'}
        </button>
      </div>
    );
  }

  if (error || !snapshot) {
    return (
      <div data-testid="dossier-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error ?? 'Dossier unavailable.'}</ErrorLine>
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

  return (
    <div data-testid="dossier-ready">
      {/* Thin KB header: version + coverage + re-assemble. */}
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
          <KbStat label="Version" value={`v${snapshot.version ?? '—'}`} />
          <KbStat label="Coverage" value={`${Math.round((snapshot.coverage_score ?? 0) * 100)}%`} />
          <KbStat label="Facts" value={String(snapshot.fact_count ?? 0)} />
        </div>
        <button
          data-testid="dossier-reassemble"
          onClick={assemble}
          disabled={assembling}
          style={{
            padding: '7px 14px',
            fontFamily: 'var(--font-mono)', fontSize: 11,
            letterSpacing: '0.04em', textTransform: 'uppercase',
            borderRadius: 'var(--radius-pill)', border: 'none',
            cursor: assembling ? 'wait' : 'pointer',
            background: 'var(--color-surface-3, var(--color-surface))',
            color: 'var(--color-ink-2)',
            opacity: assembling ? 0.6 : 1,
          }}
        >
          {assembling ? 'Re-assembling…' : 'Re-assemble'}
        </button>
      </div>

      <EngagementDossierPage
        scope={{ focalAsset: engagement.asset, engagementName: engagement.name }}
        domains={toDomainViews(snapshot)}
        onJumpToDomain={jumpToDomain}
        onOpenFact={() => { /* fact drill-in is a later loop */ }}
        onMarkComplete={() => onMarkComplete?.()}
      />
    </div>
  );
}

// ── small atoms ────────────────────────────────────────────────────

function Centered({ children, testId, tone }: { children: React.ReactNode; testId: string; tone: string }) {
  return (
    <div
      data-testid={testId}
      style={{
        padding: 'var(--space-7)',
        color: tone,
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
      }}
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
