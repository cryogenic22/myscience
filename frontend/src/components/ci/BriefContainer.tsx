/**
 * UX-Brief — BriefContainer.
 *
 * The Brief & Scope stage: renders the engagement's Business Context Brief
 * (situation, strategic decisions the war-game must inform, competitive set,
 * success criteria, constraints, sign-off status) instead of the placeholder.
 *
 * Read view. Authoring happens in the create-engagement flow (Loop B2); a
 * missing brief shows a "not authored yet" state rather than an editor.
 *
 * States: loading → not-created (404 → null) → ready → error.
 */
import { useCallback, useEffect, useState } from 'react';
import { engagementBriefApi, type BusinessContextBriefDTO, type EngagementDTO } from '../../api';
import EntityComments from './EntityComments';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

const THREAT_TONE: Record<string, string> = {
  high: 'var(--color-red, #b91c1c)',
  medium: 'var(--color-amber)',
  low: 'var(--color-ink-3)',
};

export default function BriefContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const [brief, setBrief] = useState<BusinessContextBriefDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [notCreated, setNotCreated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotCreated(false);
    engagementBriefApi.get(eid)
      .then((b) => { if (!cancelled) { if (b) setBrief(b); else setNotCreated(true); } })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid]);

  useEffect(() => load(), [load]);

  if (loading) {
    return <Centered testId="brief-loading" tone="var(--color-ink-3)">Loading brief…</Centered>;
  }

  if (notCreated) {
    return (
      <div
        data-testid="brief-empty"
        style={{
          padding: 'var(--space-7)', background: 'var(--color-surface)',
          borderRadius: 'var(--radius-panel)', boxShadow: 'var(--shadow-sm)',
          color: 'var(--color-ink-2)', maxWidth: 640,
        }}
      >
        <Kicker>Brief · not authored yet</Kicker>
        <p style={{ margin: '0 0 6px', fontSize: 18, fontFamily: 'var(--font-display)', color: 'var(--color-ink)' }}>
          No business context brief for {engagement.name}
        </p>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'var(--color-ink-3)' }}>
          The brief sets the situation, the strategic decisions the war-game must
          inform, and the competitive set. It's authored when the engagement is
          created — re-open the create flow to add one.
        </p>
      </div>
    );
  }

  if (error || !brief) {
    return (
      <div data-testid="brief-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error ?? 'Brief unavailable.'}</ErrorLine>
        <button
          onClick={load}
          style={{
            marginTop: 12, padding: '8px 14px', fontFamily: 'var(--font-mono)', fontSize: 12,
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
    <main
      data-testid="brief-ready"
      role="main"
      aria-label="Brief"
      style={{
        display: 'flex', flexDirection: 'column', gap: 22,
        padding: '24px 28px 40px', background: 'var(--color-bg)',
        color: 'var(--color-ink-2)', fontFamily: 'var(--font-body)', minHeight: '100%',
      }}
    >
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 18, borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
          Stage 01 · Brief &amp; Scope
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 400, color: 'var(--color-ink)', letterSpacing: '-0.014em', margin: 0 }}>
            {engagement.name}
          </h1>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--color-ink-3)' }}>
            {brief.focal_asset} · {brief.situation}
          </span>
          <span
            data-testid="brief-signoff"
            style={{
              marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11,
              letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 600,
              color: brief.signed_off ? 'var(--color-green, #15803d)' : 'var(--color-amber)',
            }}
          >
            {brief.signed_off ? '✓ Signed off' : '○ Draft'}
          </span>
        </div>
      </header>

      <Section label="Strategic decisions the war-game must inform">
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {brief.strategic_decisions.map((d, i) => (
            <li key={i} style={{ padding: '12px 14px', background: 'var(--color-surface)', border: '1px solid var(--color-line)', borderLeft: '3px solid var(--color-accent)' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 500, color: 'var(--color-ink)', marginBottom: 4 }}>{d.statement}</div>
              <div style={{ fontSize: 12.5, color: 'var(--color-ink-3)', lineHeight: 1.5 }}>{d.rationale}</div>
            </li>
          ))}
        </ul>
      </Section>

      {brief.competitive_set.length > 0 && (
        <Section label="Competitive set">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {brief.competitive_set.map((t, i) => (
              <span key={i} style={{ display: 'inline-flex', flexDirection: 'column', gap: 2, padding: '8px 12px', background: 'var(--color-surface)', border: `1px solid var(--color-line)`, borderLeft: `3px solid ${THREAT_TONE[t.threat_level] ?? 'var(--color-line-2)'}` }}>
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-ink)' }}>{t.entity_ref}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: THREAT_TONE[t.threat_level] ?? 'var(--color-ink-3)' }}>{t.threat_level} threat</span>
                {t.note && <span style={{ fontSize: 11.5, color: 'var(--color-ink-3)' }}>{t.note}</span>}
              </span>
            ))}
          </div>
        </Section>
      )}

      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
        {brief.success_criteria.length > 0 && (
          <Section label="Success criteria">
            <BulletList items={brief.success_criteria} />
          </Section>
        )}
        {brief.constraints.length > 0 && (
          <Section label="Constraints">
            <BulletList items={brief.constraints} />
          </Section>
        )}
      </div>

      {/* UX08 — collaboration on the brief (reuses the generic EntityComments). */}
      <section style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 16 }}>
        <EntityComments targetType="brief" targetId={brief.id} title="Brief discussion" />
      </section>

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

// ── atoms ──────────────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section style={{ flex: '1 1 280px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 12 }}>
        {label}
      </div>
      {children}
    </section>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((s, i) => (
        <li key={i} style={{ fontSize: 13.5, color: 'var(--color-ink-2)', lineHeight: 1.5 }}>{s}</li>
      ))}
    </ul>
  );
}

function Centered({ children, testId, tone }: { children: React.ReactNode; testId: string; tone: string }) {
  return (
    <div data-testid={testId} style={{ padding: 'var(--space-7)', color: tone, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      {children}
    </div>
  );
}

function Kicker({ children }: { children: React.ReactNode }) {
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
