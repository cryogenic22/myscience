/**
 * F7 — EngagementDossierPage: 8 ZS domains + visual elements + typed facts.
 *
 * Stage 3 of the engagement lifecycle. The dossier IS the read of the
 * facts — not a static document. Each fact carries a class glyph
 * (◇/◆/◈/✦), and visual-eligible domains get a tailored visualisation
 * (patient journey, competitor table, payer landscape) per Riya's
 * feedback that prose-only dossiers feel under-built.
 *
 * NOTE: Distinct from the legacy `DossierPage` (PB-301 scaffold) which
 * renders a per-entity dossier at `/dossier/:entityType/:slug`. This is
 * the engagement-stage dossier — the v7 ZS-domain read.
 *
 * Headless. Theme-aware via CSS vars.
 */
import type { ReactNode } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export const DOSSIER_DOMAINS = [
  'disease_and_patient',
  'clinical_profile',
  'competitive',
  'pricing_and_access',
  'commercial_operational',
  'hcp_and_patient',
  'pipeline_and_macro',
  'wargame_specific',
] as const;
export type DossierDomain = (typeof DOSSIER_DOMAINS)[number];

export type Priority = 'critical' | 'high' | 'medium';
export type DomainState = 'complete' | 'in_progress' | 'gap';
export type FactClass = 'reference' | 'corporate' | 'signal' | 'inferred';

const DOMAIN_LABEL: Record<DossierDomain, string> = {
  disease_and_patient:    'Disease & Patient',
  clinical_profile:       'Clinical Profile',
  competitive:            'Competitive',
  pricing_and_access:     'Pricing & Access',
  commercial_operational: 'Commercial & Operational',
  hcp_and_patient:        'HCP & Patient',
  pipeline_and_macro:     'Pipeline & Macro',
  wargame_specific:       'Wargame-Specific',
};

export const FACT_CLASS_GLYPH: Record<FactClass, string> = {
  reference: '◇',
  corporate: '◆',
  signal:    '◈',
  inferred:  '✦',
};

export const FACT_CLASS_COLOR: Record<FactClass, string> = {
  reference: 'var(--color-teal, var(--color-accent))',
  corporate: 'var(--color-accent)',
  signal:    'var(--color-green, #15803d)',
  inferred:  'var(--color-state-decide, #6C2BD9)',
};

/** What each fact class means — surfaced in the provenance panel so the
 *  confidence tier is legible, not just a glyph. */
export const FACT_CLASS_LABEL: Record<FactClass, string> = {
  reference: 'Reference — peer-reviewed / epidemiological',
  corporate: 'Corporate — filing, press release, or label',
  signal:    'Signal — derived from monitored events',
  inferred:  'Inferred — analytic derivation',
};

const STATE_GLYPH: Record<DomainState, string> = {
  complete:    '✓',
  in_progress: '◇',
  gap:         '✗',
};

const STATE_COLOR: Record<DomainState, string> = {
  complete:    'var(--color-green, #15803d)',
  in_progress: 'var(--color-amber)',
  gap:         'var(--color-red)',
};

export interface Fact {
  id: string;
  claim: string;
  factClass: FactClass;
  sourceLabel: string;
  /** PB-E05: drill-through link to the source record. */
  sourceUrl?: string;
}

export interface DomainView {
  domain: DossierDomain;
  priority: Priority;
  state: DomainState;
  /** PB-H05: per-domain evidence readiness, 0–1. */
  readiness?: number;
  facts: Fact[];
  patientJourney?: { stage: string; count: number; note: string }[];
  competitors?: { name: string; benchmark: string; status: string }[];
  payers?: { name: string; tier: string; restriction: string }[];
}

export interface EngagementDossierPageProps {
  scope: { focalAsset: string; engagementName: string };
  domains: DomainView[];
  /** PB-H05: priority-weighted engagement readiness, 0–1 (from the snapshot). */
  engagementReadiness?: number;
  onJumpToDomain: (domain: DossierDomain) => void;
  /** PB-UX03: receives the full fact so the provenance panel can show its chain. */
  onOpenFact: (fact: Fact) => void;
  onMarkComplete?: () => void;
}

// ── Atoms ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-3)',
        marginBottom: 10,
      }}
    >
      {children}
    </div>
  );
}

function priorityTone(p: Priority): { fg: string; bg: string; border: string } {
  if (p === 'critical') {
    return {
      fg: 'var(--color-accent)',
      bg: 'var(--color-accent-soft)',
      border: 'var(--color-accent)',
    };
  }
  if (p === 'high') {
    return {
      fg: 'var(--color-teal, var(--color-accent))',
      bg: 'var(--color-teal-soft, var(--color-accent-soft))',
      border: 'var(--color-teal, var(--color-accent))',
    };
  }
  return {
    fg: 'var(--color-ink-3)',
    bg: 'var(--color-surface-2)',
    border: 'var(--color-line-2)',
  };
}

function PriorityPill({ priority }: { priority: Priority }) {
  const t = priorityTone(priority);
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        padding: '2px 8px',
        background: t.bg,
        color: t.fg,
        border: `1px solid ${t.border}`,
        fontWeight: 600,
      }}
    >
      {priority}
    </span>
  );
}

function readinessTone(r: number): string {
  if (r >= 0.7) return 'var(--color-green, #15803d)';
  if (r >= 0.35) return 'var(--color-amber)';
  return 'var(--color-red)';
}

/** PB-H05: a compact readiness meter (0–1). The agent telling you where your
 *  attention is worth most — low readiness on a critical domain is a signal. */
function ReadinessBar({ readiness, width = 64 }: { readiness: number; width?: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, readiness)) * 100);
  return (
    <span
      title={`Readiness ${pct}%`}
      aria-label={`Readiness ${pct} percent`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
    >
      <span style={{ width, height: 5, borderRadius: 3, background: 'var(--color-surface-2)', overflow: 'hidden', display: 'inline-block' }}>
        <span style={{ display: 'block', width: `${pct}%`, height: '100%', background: readinessTone(readiness), borderRadius: 3 }} />
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-ink-3)' }}>{pct}%</span>
    </span>
  );
}

// ── TOC ────────────────────────────────────────────────────────────

function DomainTOC({
  domains,
  onJump,
}: {
  domains: DomainView[];
  onJump: (d: DossierDomain) => void;
}) {
  return (
    <section>
      <SectionLabel>Dossier domains · ZS Section 1.2</SectionLabel>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: 8,
        }}
      >
        {domains.map((d) => (
          <button
            type="button"
            key={d.domain}
            data-toc-domain={d.domain}
            onClick={() => onJump(d.domain)}
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              textAlign: 'left',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 13,
                fontWeight: 500,
                color: 'var(--color-ink)',
                lineHeight: 1.3,
              }}
            >
              {DOMAIN_LABEL[d.domain]}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <PriorityPill priority={d.priority} />
              <span
                style={{
                  marginLeft: 'auto',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: STATE_COLOR[d.state],
                  fontWeight: 600,
                }}
                aria-label={`${d.facts.length} facts`}
              >
                {STATE_GLYPH[d.state]} {d.facts.length}
              </span>
            </div>
            {typeof d.readiness === 'number' && <ReadinessBar readiness={d.readiness} />}
          </button>
        ))}
      </div>
    </section>
  );
}

// ── Visual elements ────────────────────────────────────────────────

function PatientJourney({ stages }: { stages: NonNullable<DomainView['patientJourney']> }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${stages.length}, 1fr)`,
        gap: 0,
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-line)',
        marginBottom: 14,
      }}
    >
      {stages.map((s, i) => {
        const next = i < stages.length - 1;
        return (
          <div
            key={s.stage}
            style={{
              padding: '14px 14px',
              borderRight: next ? '1px solid var(--color-line)' : 'none',
              position: 'relative',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9.5,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-3)',
                marginBottom: 4,
              }}
            >
              Stage {i + 1}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--color-ink)',
                marginBottom: 4,
              }}
            >
              {s.stage}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 16,
                fontWeight: 600,
                color: 'var(--color-accent)',
                marginBottom: 4,
              }}
            >
              {s.count.toLocaleString()}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--color-ink-3)', lineHeight: 1.4 }}>
              {s.note}
            </div>
            {next && (
              <div
                aria-hidden
                style={{
                  position: 'absolute',
                  right: -8,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 14,
                  color: 'var(--color-ink-3)',
                  background: 'var(--color-surface-2)',
                  padding: '0 2px',
                  zIndex: 1,
                }}
              >
                →
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CompetitorTable({ competitors }: { competitors: NonNullable<DomainView['competitors']> }) {
  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        marginBottom: 14,
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
      }}
    >
      <thead style={{ background: 'var(--color-surface-2)' }}>
        <tr>
          {['Asset', 'Benchmark', 'Status'].map((h) => (
            <th
              key={h}
              scope="col"
              style={{
                padding: '8px 12px',
                textAlign: 'left',
                fontFamily: 'var(--font-mono)',
                fontSize: 9.5,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-3)',
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {competitors.map((c) => (
          <tr key={c.name} style={{ borderTop: '1px solid var(--color-line-soft, var(--color-line))' }}>
            <td style={{ padding: '8px 12px', fontFamily: 'var(--font-display)', fontWeight: 500, color: 'var(--color-ink)' }}>
              {c.name}
            </td>
            <td style={{ padding: '8px 12px', fontSize: 13, color: 'var(--color-ink-2)' }}>{c.benchmark}</td>
            <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-3)' }}>
              {c.status}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PayerLandscape({ payers }: { payers: NonNullable<DomainView['payers']> }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: 8,
        marginBottom: 14,
      }}
    >
      {payers.map((p) => (
        <div
          key={p.name}
          style={{
            padding: '10px 12px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
            borderLeft: '3px solid var(--color-accent)',
          }}
        >
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 14, color: 'var(--color-ink)' }}>
            {p.name}
          </div>
          <div
            style={{
              display: 'flex',
              gap: 10,
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
              marginTop: 4,
            }}
          >
            <span>{p.tier}</span>
            <span style={{ color: 'var(--color-amber)' }}>{p.restriction}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Facts list ────────────────────────────────────────────────────

function FactsList({ facts, onOpenFact }: { facts: Fact[]; onOpenFact: (fact: Fact) => void }) {
  if (facts.length === 0) {
    return (
      <div
        style={{
          padding: 16,
          border: '1px dashed var(--color-line-2)',
          color: 'var(--color-ink-3)',
          fontStyle: 'italic',
          fontSize: 13,
        }}
      >
        No facts yet for this domain — return to Sources stage to wire connectors that surface evidence here.
      </div>
    );
  }
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {facts.map((f) => (
        <li
          key={f.id}
          data-fact-id={f.id}
          data-fact-class={f.factClass}
          onClick={() => onOpenFact(f)}
          title="View provenance"
          style={{
            display: 'grid',
            gridTemplateColumns: '24px 1fr 170px',
            gap: 10,
            padding: '8px 12px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
            cursor: 'pointer',
            transition: 'background 80ms ease',
          }}
        >
          <span
            aria-label={`${f.factClass} fact`}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 14,
              color: FACT_CLASS_COLOR[f.factClass],
              fontWeight: 600,
            }}
          >
            {FACT_CLASS_GLYPH[f.factClass]}
          </span>
          <span style={{ fontSize: 13.5, color: 'var(--color-ink)', lineHeight: 1.45 }}>{f.claim}</span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
              textAlign: 'right',
              display: 'flex',
              gap: 4,
              justifyContent: 'flex-end',
              alignItems: 'baseline',
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.sourceLabel}</span>
            {f.sourceUrl && <span aria-label="has source link" style={{ color: 'var(--color-accent)' }}>↗</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ── Section ───────────────────────────────────────────────────────

function DomainSection({
  d,
  onOpenFact,
}: {
  d: DomainView;
  onOpenFact: (fact: Fact) => void;
}) {
  const labelId = `domain-${d.domain}`;
  return (
    <section
      data-domain={d.domain}
      aria-labelledby={labelId}
      style={{
        background: 'var(--color-bg)',
        paddingBottom: 18,
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 1,
          background: 'var(--color-bg)',
          paddingBottom: 10,
          marginBottom: 14,
          display: 'flex',
          alignItems: 'baseline',
          gap: 12,
        }}
      >
        <h2
          id={labelId}
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 500,
            color: 'var(--color-ink)',
            letterSpacing: '-0.01em',
            margin: 0,
          }}
        >
          {DOMAIN_LABEL[d.domain]}
        </h2>
        <PriorityPill priority={d.priority} />
        {typeof d.readiness === 'number' && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center' }}>
            <ReadinessBar readiness={d.readiness} width={80} />
          </span>
        )}
        <span
          style={{
            marginLeft: typeof d.readiness === 'number' ? 0 : 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: STATE_COLOR[d.state],
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          {STATE_GLYPH[d.state]} {d.state} · {d.facts.length} facts
        </span>
      </header>

      {d.domain === 'disease_and_patient' && d.patientJourney && (
        <PatientJourney stages={d.patientJourney} />
      )}
      {d.domain === 'competitive' && d.competitors && (
        <CompetitorTable competitors={d.competitors} />
      )}
      {d.domain === 'pricing_and_access' && d.payers && (
        <PayerLandscape payers={d.payers} />
      )}

      <FactsList facts={d.facts} onOpenFact={onOpenFact} />
    </section>
  );
}

// ── Main component ────────────────────────────────────────────────

export function EngagementDossierPage(props: EngagementDossierPageProps) {
  const { scope, domains, engagementReadiness, onJumpToDomain, onOpenFact, onMarkComplete } = props;
  const totalFacts = domains.reduce((acc, d) => acc + d.facts.length, 0);
  const completed = domains.filter((d) => d.state === 'complete').length;

  return (
    <main
      role="main"
      aria-label="Engagement Dossier"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 26,
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          paddingBottom: 18,
          borderBottom: '1px solid var(--color-divider)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          Stage 03 · Dossier
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 30,
              fontWeight: 400,
              color: 'var(--color-ink)',
              letterSpacing: '-0.014em',
              margin: 0,
            }}
          >
            Dossier — eight domains
          </h1>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11.5,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
            }}
          >
            {scope.engagementName} · {scope.focalAsset}
          </span>
          <span
            style={{
              marginLeft: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 14,
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--color-ink-2)',
            }}
          >
            <span>
              <strong style={{ color: 'var(--color-ink)' }}>{completed}</strong>/{domains.length} complete ·{' '}
              <strong style={{ color: 'var(--color-ink)' }}>{totalFacts}</strong> facts
            </span>
            {typeof engagementReadiness === 'number' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ letterSpacing: '0.04em' }}>readiness</span>
                <ReadinessBar readiness={engagementReadiness} width={90} />
              </span>
            )}
          </span>
        </div>
      </header>

      <DomainTOC domains={domains} onJump={onJumpToDomain} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
        {domains.map((d) => (
          <DomainSection key={d.domain} d={d} onOpenFact={onOpenFact} />
        ))}
      </div>

      {/* Footer */}
      {onMarkComplete && (
      <footer
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 12,
          paddingTop: 16,
          borderTop: '1px solid var(--color-divider)',
        }}
      >
        <button
          type="button"
          onClick={onMarkComplete}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            padding: '8px 16px',
            background: 'var(--color-accent)',
            color: 'var(--color-surface)',
            border: '1px solid var(--color-accent)',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          Mark stage complete →
        </button>
      </footer>
      )}
    </main>
  );
}
