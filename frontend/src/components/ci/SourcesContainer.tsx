/**
 * UX07 — SourcesContainer.
 *
 * The Sources stage: which sources feed THIS engagement's dossier, how much
 * each contributes, which domains they touch, and the confidence-class mix.
 * Read-only coverage view (document upload / source management is deferred —
 * those live in the future Data Hub epic E17, not the engagement stages).
 *
 * Derived from the dossier snapshot (GET /engagements/{eid}/sources). Mirrors
 * the container state machine: loading → not-assembled (assemble CTA) → ready
 * → error.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  engagementSourcesApi,
  dossierKbApi,
  DossierNotAssembled,
  type EngagementSourcesResponse,
  type EngagementSourceRow,
  type EngagementDTO,
} from '../../api';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

const CLASS_GLYPH: Record<string, string> = {
  reference: '◇', corporate: '◆', signal: '◈', inferred: '✦', internal: '▣',
};

export default function SourcesContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const [data, setData] = useState<EngagementSourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAssembled, setNotAssembled] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotAssembled(false);
    engagementSourcesApi.get(eid)
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

  if (loading) {
    return <Centered testId="sources-loading" tone="var(--color-ink-3)">Loading sources…</Centered>;
  }

  if (notAssembled) {
    return (
      <div
        data-testid="sources-empty"
        style={{
          padding: 'var(--space-7)', background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)', boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)', maxWidth: 640,
        }}
      >
        <SectionKicker>Sources · no dossier yet</SectionKicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          Assemble the dossier to see source coverage
        </p>
        <p style={{ margin: '0 0 var(--space-5)', fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          Source coverage is derived from the dossier — it shows which sources fed
          {' '}{engagement.name} and where the evidence is concentrated.
        </p>
        {error && <ErrorLine>{error}</ErrorLine>}
        <button
          data-testid="sources-assemble"
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
      <div data-testid="sources-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error ?? 'Sources unavailable.'}</ErrorLine>
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

  const maxFacts = Math.max(1, ...data.sources.map((s) => s.fact_count));

  return (
    <main
      data-testid="sources-ready"
      role="main"
      aria-label="Sources"
      style={{
        display: 'flex', flexDirection: 'column', gap: 22,
        padding: '24px 28px 40px', background: 'var(--color-bg)',
        color: 'var(--color-ink-2)', fontFamily: 'var(--font-body)', minHeight: '100%',
      }}
    >
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 18, borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
          Stage 02 · Sources
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 400, color: 'var(--color-ink)', letterSpacing: '-0.014em', margin: 0 }}>
            What's feeding this dossier.
          </h1>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--color-ink-3)' }}>
            {engagement.name} · {engagement.asset}
          </span>
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-2)' }}>
            <strong style={{ color: 'var(--color-ink)' }}>{data.source_count} sources</strong>
            {' · '}<strong style={{ color: 'var(--color-accent)' }}>{data.total_facts} facts</strong>
            {' · '}{Math.round((data.coverage_score ?? 0) * 100)}% coverage
          </span>
        </div>
      </header>

      {data.sources.length === 0 ? (
        <div style={{ padding: 20, border: '1px dashed var(--color-line-2)', color: 'var(--color-ink-3)', fontStyle: 'italic', textAlign: 'center' }}>
          No sources have contributed facts yet — assemble or enrich the dossier.
        </div>
      ) : (
        <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.sources.map((s) => (
            <SourceCard key={s.source} row={s} maxFacts={maxFacts} />
          ))}
        </ul>
      )}

      <footer style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, paddingTop: 16, borderTop: '1px solid var(--color-divider)' }}>
        <button
          type="button"
          aria-label="Mark stage complete"
          onClick={() => onMarkComplete?.()}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.16em',
            textTransform: 'uppercase', padding: '8px 16px',
            background: 'var(--color-accent)', color: 'var(--color-surface)',
            border: '1px solid var(--color-accent)', cursor: 'pointer', fontWeight: 600,
          }}
        >
          Mark stage complete →
        </button>
      </footer>
    </main>
  );
}

function SourceCard({ row, maxFacts }: { row: EngagementSourceRow; maxFacts: number }) {
  const pct = Math.round((row.fact_count / maxFacts) * 100);
  return (
    <li
      data-source={row.source}
      style={{
        padding: '14px 16px', background: 'var(--color-surface)',
        border: '1px solid var(--color-line)', borderLeft: '3px solid var(--color-accent)',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 500, color: 'var(--color-ink)' }}>
          {row.source}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-2)' }}>
          <strong style={{ color: 'var(--color-ink)' }}>{row.fact_count}</strong> facts
        </span>
      </div>
      {/* contribution bar */}
      <div style={{ height: 6, background: 'var(--color-surface-2)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--color-accent)' }} />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--color-ink-3)', letterSpacing: '0.04em' }}>
          {row.domains.join(' · ')}
        </span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 8 }}>
          {Object.entries(row.classes).map(([cls, n]) => (
            <span key={cls} title={cls} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-2)' }}>
              {CLASS_GLYPH[cls] ?? '·'} {n}
            </span>
          ))}
        </span>
      </div>
    </li>
  );
}

// ── small atoms ────────────────────────────────────────────────────

function Centered({ children, testId, tone }: { children: React.ReactNode; testId: string; tone: string }) {
  return (
    <div data-testid={testId} style={{ padding: 'var(--space-7)', color: tone, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      {children}
    </div>
  );
}

function SectionKicker({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 12 }}>
      {children}
    </div>
  );
}

function ErrorLine({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: '0 0 4px', color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
      {children}
    </p>
  );
}
