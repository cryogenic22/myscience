/**
 * F6 — SourcesPage: named outlets with real article URLs.
 *
 * Closes Riya's "sources are classes, not named outlets with links" gap.
 * The page surfaces the 7 source classes (Helix Engine Design §2.1) as
 * tiles, with each named outlet listed below with its real status,
 * cadence, access type, and a click-through to its latest article when
 * one is available.
 *
 * Click a class tile to filter the outlets table by that class. Gap-status
 * outlets surface "Plan primary research" inline — the affordance Riya
 * called out as missing in v7.
 *
 * Headless — props in, callbacks out.
 */
import { useState } from 'react';

export type SourceClassId =
  | 'regulatory_api'
  | 'scientific_literature'
  | 'corporate_filings'
  | 'corporate_communications'
  | 'scientific_presentations'
  | 'payer_pricing'
  | 'internal_documents';

export type AccessType = 'free' | 'paid' | 'mixed' | 'internal';
export type OutletStatus = 'connected' | 'partial' | 'gap';

export interface SourceClass {
  id: SourceClassId;
  label: string;
  connected: number;
  total: number;
}

export interface Outlet {
  id: string;
  name: string;
  classId: SourceClassId;
  access: AccessType;
  cadence: string;
  status: OutletStatus;
  latestArticle?: {
    title: string;
    url: string;
    publishedAt: string;
  } | null;
}

export interface SourcesPageProps {
  scope: { focalAsset: string; engagementName: string };
  classes: SourceClass[];
  outlets: Outlet[];
  onPlanResearch: (outletId: string) => void;
  onOpenArticle: (outletId: string, url: string) => void;
}

// ── Tones ──────────────────────────────────────────────────────────

function classTileTone(c: SourceClass): { tone: string; status: string } {
  if (c.total === 0) return { tone: 'var(--color-ink-4)', status: 'empty' };
  const ratio = c.connected / c.total;
  if (c.connected === 0) return { tone: 'var(--color-red)', status: 'gap' };
  if (ratio >= 1) return { tone: 'var(--color-green, #15803d)', status: 'connected' };
  return { tone: 'var(--color-amber)', status: 'partial' };
}

function outletStatusTone(s: OutletStatus): string {
  switch (s) {
    case 'connected': return 'var(--color-green, #15803d)';
    case 'partial':   return 'var(--color-amber)';
    case 'gap':       return 'var(--color-red)';
  }
}

function accessLabel(a: AccessType): string {
  switch (a) {
    case 'free': return 'Free';
    case 'paid': return 'Paid';
    case 'mixed': return 'Mixed';
    case 'internal': return 'Internal';
  }
}

// ── Section atom ───────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
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

// ── Main component ────────────────────────────────────────────────

export function SourcesPage(props: SourcesPageProps) {
  const { scope, classes, outlets, onPlanResearch, onOpenArticle } = props;
  const [filterClass, setFilterClass] = useState<SourceClassId | null>(null);

  const covered = classes.reduce((acc, c) => acc + c.connected, 0);
  const total   = classes.reduce((acc, c) => acc + c.total, 0);

  const visibleOutlets = filterClass
    ? outlets.filter((o) => o.classId === filterClass)
    : outlets;

  // Lookup from classId to label (for the table column)
  const classLabel: Record<SourceClassId, string> = classes.reduce(
    (acc, c) => ({ ...acc, [c.id]: c.label }),
    {} as Record<SourceClassId, string>,
  );

  return (
    <main
      role="main"
      aria-label="Sources and Gaps"
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
          Stage 02 · Sources & Gaps
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
            Source Register
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
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--color-ink-2)',
              letterSpacing: '0.04em',
            }}
          >
            Coverage <strong style={{ color: 'var(--color-ink)' }}>{covered} / {total}</strong>
          </span>
        </div>
      </header>

      {/* Class tile grid */}
      <section>
        <SectionLabel>Source classes · click to filter</SectionLabel>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 10,
          }}
        >
          {classes.map((c) => {
            const { tone, status } = classTileTone(c);
            const isActive = filterClass === c.id;
            return (
              <div
                key={c.id}
                data-class={c.id}
                data-status={status}
                onClick={() => setFilterClass(isActive ? null : c.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    setFilterClass(isActive ? null : c.id);
                  }
                }}
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-surface)',
                  border: `1px solid ${isActive ? 'var(--color-accent)' : 'var(--color-line)'}`,
                  borderLeft: `3px solid ${tone}`,
                  cursor: 'pointer',
                  transition: 'background 80ms ease',
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 13.5,
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                    marginBottom: 8,
                    lineHeight: 1.3,
                  }}
                >
                  {c.label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10.5,
                    color: 'var(--color-ink-3)',
                    letterSpacing: '0.04em',
                  }}
                >
                  <span style={{ color: tone, fontWeight: 600 }}>
                    {c.connected}
                  </span>{' '}
                  /  {c.total} outlets
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Outlets table */}
      <section>
        <SectionLabel>
          Named outlets {filterClass ? `· filtered to ${classLabel[filterClass]}` : `· ${outlets.length} total`}
        </SectionLabel>
        {visibleOutlets.length === 0 ? (
          <div
            style={{
              padding: 18,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontSize: 13.5,
              fontStyle: 'italic',
            }}
          >
            No outlets configured. Add one →
          </div>
        ) : (
          <table
            aria-label="Named outlets"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: 'var(--font-body)',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
            }}
          >
            <thead>
              <tr style={{ background: 'var(--color-surface-2)' }}>
                {['Outlet', 'Class', 'Access', 'Cadence', 'Status', 'Latest'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    style={{
                      padding: '10px 12px',
                      textAlign: 'left',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 9.5,
                      letterSpacing: '0.16em',
                      textTransform: 'uppercase',
                      color: 'var(--color-ink-3)',
                      borderBottom: '1px solid var(--color-line)',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleOutlets.map((o) => {
                const tone = outletStatusTone(o.status);
                return (
                  <tr
                    key={o.id}
                    data-outlet={o.id}
                    style={{ borderTop: '1px solid var(--color-line-soft, var(--color-line))' }}
                  >
                    <td
                      style={{
                        padding: '10px 12px',
                        fontFamily: 'var(--font-display)',
                        fontSize: 14,
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                      }}
                    >
                      {o.name}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        fontSize: 12.5,
                        color: 'var(--color-ink-2)',
                      }}
                    >
                      {classLabel[o.classId] ?? o.classId}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--color-ink-3)',
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                      }}
                    >
                      {accessLabel(o.access)}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--color-ink-3)',
                      }}
                    >
                      {o.cadence}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9.5,
                          letterSpacing: '0.16em',
                          textTransform: 'uppercase',
                          padding: '2px 7px',
                          border: `1px solid ${tone}`,
                          color: tone,
                          fontWeight: 600,
                        }}
                      >
                        {o.status}
                      </span>
                      {o.status === 'gap' && (
                        <button
                          type="button"
                          data-action="plan-research"
                          onClick={() => onPlanResearch(o.id)}
                          style={{
                            display: 'block',
                            marginTop: 6,
                            background: 'transparent',
                            border: '1px solid var(--color-amber)',
                            color: 'var(--color-amber)',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 9.5,
                            letterSpacing: '0.12em',
                            textTransform: 'uppercase',
                            padding: '3px 8px',
                            cursor: 'pointer',
                          }}
                        >
                          Plan primary research →
                        </button>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', maxWidth: 320 }}>
                      {o.latestArticle ? (
                        <a
                          href={o.latestArticle.url}
                          data-action="open-article"
                          data-outlet={o.id}
                          onClick={(e) => {
                            e.preventDefault();
                            onOpenArticle(o.id, o.latestArticle!.url);
                          }}
                          style={{
                            color: 'var(--color-accent)',
                            textDecoration: 'none',
                            fontSize: 12.5,
                            display: 'inline-block',
                            maxWidth: 320,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={`${o.latestArticle.title} · ${o.latestArticle.publishedAt}`}
                        >
                          {o.latestArticle.title}
                        </a>
                      ) : (
                        <span style={{ color: 'var(--color-ink-4)', fontSize: 13 }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
