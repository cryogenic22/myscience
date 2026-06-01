/**
 * UX05 — GapsContainer.
 *
 * Wires the (already-built, headless) GapsPage to the live dossier gaps
 * (H04: actionable collection gaps — what's missing in each domain, how to
 * fill it, how much it matters). Mirrors DossierContainer's state machine.
 *
 * States:
 *   - loading       → fetching gaps
 *   - not-assembled → no dossier yet; offer to assemble one (gaps derive from it)
 *   - error         → load/assemble failed
 *   - ready         → render GapsPage + a thin header (coverage + counts)
 *
 * Remediation (primary_research / accept / descope) is CLIENT-SIDE for now —
 * there is no gap-remediation persistence table yet (logged PB-UX05b). It is
 * fully functional in-session: it drives the readiness banner + the
 * "mark complete" gate, but does not survive a reload.
 *
 * Backend gap shape: {domain, priority, importance, text, method, thin}.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  dossierKbApi,
  DossierNotAssembled,
  type DossierGapsDTO,
  type EngagementDTO,
} from '../../api';
import { GapsPage, type Gap, type Importance, type Remediation } from '../../pages/GapsPage';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

function importanceFromPriority(priority: string): Importance {
  if (priority === 'critical') return 'critical';
  if (priority === 'high') return 'high';
  return 'medium';
}

function humanizeDomain(domain: string): string {
  return domain.replace(/_/g, ' ');
}

export default function GapsContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const [data, setData] = useState<DossierGapsDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAssembled, setNotAssembled] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // gapId → chosen remediation (client-side; see PB-UX05b).
  const [remediations, setRemediations] = useState<Record<string, Remediation>>({});

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotAssembled(false);
    dossierKbApi.gaps(eid)
      .then((d) => { if (!cancelled) setData(d); })
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
      await dossierKbApi.assemble(eid);
      load();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setAssembling(false);
    }
  };

  // Map backend gaps → GapsPage.Gap, overlaying any client-side remediation.
  const gaps: Gap[] = useMemo(() => {
    if (!data) return [];
    return data.gaps.map((g) => {
      const id = `gap-${g.domain}`;
      return {
        id,
        domain: humanizeDomain(g.domain),
        importance: importanceFromPriority(g.priority),
        question: g.text,
        fillMethod: g.method,
        remediation: remediations[id] ?? 'pending',
      } as Gap;
    });
  }, [data, remediations]);

  if (loading) {
    return (
      <Centered testId="gaps-loading" tone="var(--color-ink-3)">
        Loading gaps…
      </Centered>
    );
  }

  if (notAssembled) {
    return (
      <div
        data-testid="gaps-empty"
        style={{
          padding: 'var(--space-7)',
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)',
          boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)',
          maxWidth: 640,
        }}
      >
        <SectionKicker>Gaps · no dossier yet</SectionKicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          Assemble the dossier to surface gaps
        </p>
        <p style={{ margin: '0 0 var(--space-5)', fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          Intelligence gaps are derived from the dossier — the domains with no (or
          thin) evidence become the collection priorities for {engagement.name}.
        </p>
        {error && <ErrorLine>{error}</ErrorLine>}
        <button
          data-testid="gaps-assemble"
          onClick={assemble}
          disabled={assembling}
          style={{
            padding: '11px 20px', fontSize: 14, fontWeight: 500,
            borderRadius: 'var(--radius-pill)', border: 'none',
            cursor: assembling ? 'wait' : 'pointer',
            background: 'var(--color-ink)', color: 'var(--color-bg)',
            opacity: assembling ? 0.6 : 1,
          }}
        >
          {assembling ? 'Assembling…' : 'Assemble dossier'}
        </button>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div data-testid="gaps-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error ?? 'Gaps unavailable.'}</ErrorLine>
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
    <div data-testid="gaps-ready">
      {/* Thin header: coverage + counts. */}
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
          <KbStat label="Coverage" value={`${Math.round((data.coverage_score ?? 0) * 100)}%`} />
          <KbStat label="Open gaps" value={String(gaps.length)} />
          <KbStat
            label="Unresolved"
            value={String(gaps.filter((g) => g.remediation === 'pending').length)}
          />
        </div>
      </div>

      <GapsPage
        scope={{ engagementName: engagement.name, focalAsset: engagement.asset }}
        gaps={gaps}
        onSetRemediation={(gapId, remediation) =>
          setRemediations((prev) => ({ ...prev, [gapId]: remediation }))}
        onMarkComplete={() => onMarkComplete?.()}
      />
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
