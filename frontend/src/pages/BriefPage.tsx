/**
 * F5 — BriefPage: the first stage of the engagement lifecycle.
 *
 * Renders the Z4 Business Context Brief + Z5 priority matrix as the
 * engagement's scoping artifact. Launch-only per Riya's feedback;
 * Defense/LCM are drift-guarded with a stub.
 *
 * Sections (top-to-bottom): header · strategic decisions · competitive
 * set · priority matrix · success criteria + constraints · sign-off footer.
 *
 * Headless — props in, callbacks out. Routing layer wires the API.
 */
import { ReactNode } from 'react';

// Mirrors services/priority_matrix.py
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
const PRIORITY_CYCLE: Record<Priority, Priority> = {
  critical: 'high',
  high: 'medium',
  medium: 'critical',
};

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

type ThreatLevel = 'primary' | 'secondary' | 'watch';

export interface BriefData {
  id: string;
  focalAsset: string;
  situation: 'launch';
  strategicDecisions: { statement: string; rationale: string }[];
  competitiveSet: {
    entityRef: string;
    threatLevel: ThreatLevel;
    note: string;
  }[];
  successCriteria: string[];
  constraints: string[];
  signedOff: boolean;
  signedOffBy?: string | null;
  signedOffAt?: string | null;
}

export interface PriorityMatrixData {
  cells: Record<DossierDomain, Priority>;
}

export interface BriefPageProps {
  brief: BriefData;
  matrix: PriorityMatrixData;
  onSignOff: () => void;
  onCellEdit?: (domain: DossierDomain, priority: Priority) => void;
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
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  );
}

function SituationPill({ situation }: { situation: 'launch' }) {
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        padding: '3px 10px',
        background: 'var(--color-accent-soft)',
        color: 'var(--color-accent)',
        border: '1px solid var(--color-accent)',
        fontWeight: 600,
      }}
    >
      {situation}
    </span>
  );
}

function priorityColor(p: Priority): { fg: string; bg: string; border: string } {
  switch (p) {
    case 'critical':
      return {
        fg: 'var(--color-accent)',
        bg: 'var(--color-accent-soft)',
        border: 'var(--color-accent)',
      };
    case 'high':
      return {
        fg: 'var(--color-teal, var(--color-accent))',
        bg: 'var(--color-teal-soft, var(--color-accent-soft))',
        border: 'var(--color-teal, var(--color-accent))',
      };
    case 'medium':
    default:
      return {
        fg: 'var(--color-ink-3)',
        bg: 'var(--color-surface-2)',
        border: 'var(--color-line-2)',
      };
  }
}

// ── Launch-only drift guard ───────────────────────────────────────

function LaunchOnlyStub({ situation }: { situation: string }) {
  return (
    <main
      role="main"
      aria-label="Brief and Scope"
      style={{
        padding: 40,
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      <div
        style={{
          maxWidth: 520,
          margin: '60px auto',
          padding: 32,
          border: '1px dashed var(--color-line-2)',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--color-amber)',
            marginBottom: 12,
          }}
        >
          Demo supports Launch only
        </div>
        <p style={{ fontSize: 14, color: 'var(--color-ink-3)' }}>
          The current demo supports the <strong>Launch</strong> situation. This
          engagement is configured as <code>{situation}</code>; the Defense and
          LCM playbooks land in a later iteration.
        </p>
      </div>
    </main>
  );
}

// ── Sections ───────────────────────────────────────────────────────

function BriefHeader({ brief }: { brief: BriefData }) {
  return (
    <header
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        paddingBottom: 20,
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
        Stage 01 · Brief & Scope
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
          Business Context Brief
        </h1>
        <SituationPill situation={brief.situation} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {brief.focalAsset}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: brief.signedOff ? 'var(--color-green, #15803d)' : 'var(--color-amber)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          {brief.signedOff
            ? `✓ Signed off by ${brief.signedOffBy ?? '—'}`
            : '◇ Draft'}
        </span>
      </div>
    </header>
  );
}

function StrategicDecisions({ decisions }: { decisions: BriefData['strategicDecisions'] }) {
  return (
    <section>
      <SectionLabel>Strategic decisions · {decisions.length}</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {decisions.map((d, i) => (
          <article
            key={i}
            style={{
              padding: '14px 16px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              borderLeft: '3px solid var(--color-accent)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 16,
                fontWeight: 500,
                color: 'var(--color-ink)',
                marginBottom: 6,
                lineHeight: 1.4,
              }}
            >
              {d.statement}
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-ink-3)', lineHeight: 1.5 }}>
              {d.rationale}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function CompetitiveSet({ set: cs }: { set: BriefData['competitiveSet'] }) {
  if (cs.length === 0) {
    return (
      <section>
        <SectionLabel>Competitive set</SectionLabel>
        <div
          style={{
            padding: 18,
            border: '1px dashed var(--color-line-2)',
            color: 'var(--color-ink-3)',
            fontSize: 13.5,
            fontStyle: 'italic',
          }}
        >
          Awaiting primary research. The competitive set has not been confirmed
          for this engagement — sources stage will surface candidates.
        </div>
      </section>
    );
  }

  const grouped: Record<ThreatLevel, typeof cs> = {
    primary:   cs.filter((t) => t.threatLevel === 'primary'),
    secondary: cs.filter((t) => t.threatLevel === 'secondary'),
    watch:     cs.filter((t) => t.threatLevel === 'watch'),
  };

  return (
    <section>
      <SectionLabel>Competitive set · {cs.length}</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {(Object.keys(grouped) as ThreatLevel[]).map((level) => {
          const items = grouped[level];
          if (items.length === 0) return null;
          const tone =
            level === 'primary'
              ? 'var(--color-accent)'
              : level === 'secondary'
              ? 'var(--color-ink-2)'
              : 'var(--color-ink-3)';
          return (
            <section key={level}>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9.5,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: tone,
                  marginBottom: 6,
                  fontWeight: 600,
                }}
              >
                {level}
              </div>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {items.map((t, i) => (
                  <li
                    key={i}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '170px 1fr',
                      gap: 12,
                      padding: '8px 12px',
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-line)',
                    }}
                  >
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11.5,
                        color: 'var(--color-ink)',
                        fontWeight: 500,
                      }}
                    >
                      {t.entityRef}
                    </span>
                    <span style={{ fontSize: 13, color: 'var(--color-ink-2)' }}>
                      {t.note}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function PriorityMatrixGrid({
  matrix,
  onCellEdit,
}: {
  matrix: PriorityMatrixData;
  onCellEdit?: (d: DossierDomain, p: Priority) => void;
}) {
  return (
    <section>
      <SectionLabel>Priority matrix · ZS Section 1.1</SectionLabel>
      <table
        aria-label="Priority matrix"
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: 'var(--font-body)',
        }}
      >
        <thead style={{ visibility: 'collapse', height: 0 }}>
          <tr>
            <th scope="col">Domain</th>
            <th scope="col">Priority</th>
          </tr>
        </thead>
        <tbody>
          {DOSSIER_DOMAINS.map((domain) => {
            const p = matrix.cells[domain];
            const c = priorityColor(p);
            const onClick = () => {
              if (onCellEdit) onCellEdit(domain, PRIORITY_CYCLE[p]);
            };
            return (
              <tr key={domain}>
                <th
                  scope="row"
                  style={{
                    width: '60%',
                    padding: '10px 14px',
                    borderTop: '1px solid var(--color-line-soft, var(--color-line))',
                    fontFamily: 'var(--font-display)',
                    fontSize: 14,
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                    textAlign: 'left',
                  }}
                >
                  {DOMAIN_LABEL[domain]}
                </th>
                <td
                  data-domain={domain}
                  data-priority={p}
                  onClick={onClick}
                  style={{
                    padding: '10px 14px',
                    borderTop: '1px solid var(--color-line-soft, var(--color-line))',
                    cursor: onCellEdit ? 'pointer' : 'default',
                  }}
                >
                  <span
                    style={{
                      display: 'inline-block',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      letterSpacing: '0.16em',
                      textTransform: 'uppercase',
                      padding: '3px 9px',
                      background: c.bg,
                      color: c.fg,
                      border: `1px solid ${c.border}`,
                      fontWeight: 600,
                    }}
                  >
                    {p}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function CriteriaAndConstraints({
  success,
  constraints,
}: {
  success: string[];
  constraints: string[];
}) {
  return (
    <section
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 18,
      }}
    >
      <div>
        <SectionLabel>Success criteria</SectionLabel>
        {success.length === 0 ? (
          <div style={{ fontStyle: 'italic', color: 'var(--color-ink-3)', fontSize: 13 }}>
            Not yet defined.
          </div>
        ) : (
          <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-2)' }}>
            {success.map((c, i) => (
              <li key={i} style={{ marginBottom: 6, fontSize: 13.5 }}>
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <SectionLabel>Constraints</SectionLabel>
        {constraints.length === 0 ? (
          <div style={{ fontStyle: 'italic', color: 'var(--color-ink-3)', fontSize: 13 }}>
            No constraints recorded.
          </div>
        ) : (
          <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-2)' }}>
            {constraints.map((c, i) => (
              <li key={i} style={{ marginBottom: 6, fontSize: 13.5 }}>
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function SignOffFooter({
  signedOff,
  onSignOff,
}: {
  signedOff: boolean;
  onSignOff: () => void;
}) {
  return (
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
        onClick={signedOff ? undefined : onSignOff}
        disabled={signedOff}
        aria-label={signedOff ? 'Signed off' : 'Sign off'}
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          padding: '8px 16px',
          background: signedOff ? 'var(--color-surface-2)' : 'var(--color-accent)',
          color: signedOff ? 'var(--color-ink-3)' : 'var(--color-surface)',
          border: `1px solid ${signedOff ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
          cursor: signedOff ? 'not-allowed' : 'pointer',
          fontWeight: 600,
        }}
      >
        {signedOff ? '✓ Signed off' : 'Sign off →'}
      </button>
    </footer>
  );
}

// ── Main component ────────────────────────────────────────────────

export function BriefPage(props: BriefPageProps) {
  const { brief, matrix, onSignOff, onCellEdit } = props;

  if (brief.situation !== 'launch') {
    return <LaunchOnlyStub situation={brief.situation} />;
  }

  return (
    <main
      role="main"
      aria-label="Brief and Scope"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 28,
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      <BriefHeader brief={brief} />
      <StrategicDecisions decisions={brief.strategicDecisions} />
      <CompetitiveSet set={brief.competitiveSet} />
      <PriorityMatrixGrid matrix={matrix} onCellEdit={onCellEdit} />
      <CriteriaAndConstraints
        success={brief.successCriteria}
        constraints={brief.constraints}
      />
      <SignOffFooter signedOff={brief.signedOff} onSignOff={onSignOff} />
    </main>
  );
}
