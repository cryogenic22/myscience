/**
 * F8 — SynthesisPage: makes the Z2 Insight + rejected_insights load-bearing.
 *
 * Stage 4 of the engagement lifecycle. Every insight is visible with its
 * strategic-frame badge, domain, fact-citation chain, and synthesis test
 * rationale. Rejected candidates surface in a <details> disclosure as the
 * audit artifact — the procurement-grade point Priya called out.
 *
 * Riya's "insights are being hallucinated" finding is closed at the type
 * level by Z2; this page makes the closure visible to analysts.
 *
 * Defence in depth: if an insight is somehow received with zero citations
 * (a violation of the Z2 type invariant), the UI renders an integrity-error
 * marker so the violation surfaces rather than passing silently.
 *
 * Headless. Theme-aware.
 */
import { ReactNode, useState } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export type StrategicFrame = 'risk' | 'opportunity' | 'assumption' | 'trigger';

export interface FactCitation {
  factId: string;
  predicate: string;
  contribution: string;
}

export interface Insight {
  id: string;
  statement: string;
  strategicFrame: StrategicFrame;
  domain: string;
  derivedFrom: FactCitation[];
  synthesisTestRationale: string;
  createdAt?: string;
}

export interface RejectedInsight {
  id: string;
  candidateStatement: string;
  rejectionReason: string;
  derivedFrom?: FactCitation[];
}

export interface SynthesisPageProps {
  scope: { engagementName: string; focalAsset: string };
  insights: Insight[];
  rejectedInsights: RejectedInsight[];
  onOpenFact: (factId: string) => void;
  onMarkComplete: () => void;
}

// ── Tones ──────────────────────────────────────────────────────────

const FRAMES: StrategicFrame[] = ['risk', 'opportunity', 'assumption', 'trigger'];

function frameTone(f: StrategicFrame): { fg: string; bg: string; border: string } {
  switch (f) {
    case 'risk':
      return {
        fg: 'var(--color-red, #b91c1c)',
        bg: 'rgba(185, 28, 28, 0.08)',
        border: 'var(--color-red, #b91c1c)',
      };
    case 'opportunity':
      return {
        fg: 'var(--color-green, #15803d)',
        bg: 'var(--color-green-soft, rgba(21, 128, 61, 0.08))',
        border: 'var(--color-green, #15803d)',
      };
    case 'assumption':
      return {
        fg: 'var(--color-amber, #b45309)',
        bg: 'var(--color-amber-soft, rgba(180, 83, 9, 0.08))',
        border: 'var(--color-amber, #b45309)',
      };
    case 'trigger':
      return {
        fg: 'var(--color-accent)',
        bg: 'var(--color-accent-soft)',
        border: 'var(--color-accent)',
      };
  }
}

function FrameBadge({ frame }: { frame: StrategicFrame }) {
  const t = frameTone(frame);
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
      {frame}
    </span>
  );
}

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

// ── Insight card ───────────────────────────────────────────────────

function InsightCard({
  insight,
  onOpenFact,
}: {
  insight: Insight;
  onOpenFact: (id: string) => void;
}) {
  const integrity = insight.derivedFrom.length === 0;
  return (
    <li
      data-insight-id={insight.id}
      style={{
        padding: '14px 16px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${integrity ? 'var(--color-red, #b91c1c)' : frameTone(insight.strategicFrame).border}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <FrameBadge frame={insight.strategicFrame} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {insight.domain}
        </span>
        {integrity && (
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--color-red, #b91c1c)',
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            [!] Integrity error — no fact chain
          </span>
        )}
      </div>

      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 16,
          fontWeight: 500,
          color: 'var(--color-ink)',
          lineHeight: 1.4,
        }}
      >
        {insight.statement}
      </div>

      {!integrity && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            paddingTop: 6,
            borderTop: '1px dashed var(--color-line-soft, var(--color-line))',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9.5,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
              marginBottom: 4,
            }}
          >
            Derived from · {insight.derivedFrom.length} fact{insight.derivedFrom.length === 1 ? '' : 's'}
          </div>
          {insight.derivedFrom.map((c) => (
            <div
              key={c.factId}
              data-fact-id={c.factId}
              onClick={() => onOpenFact(c.factId)}
              style={{
                display: 'grid',
                gridTemplateColumns: '90px 140px 1fr',
                gap: 10,
                padding: '5px 8px',
                fontSize: 12.5,
                color: 'var(--color-ink-2)',
                cursor: 'pointer',
                background: 'var(--color-surface-2)',
                borderRadius: 2,
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--color-accent)',
                  letterSpacing: '0.04em',
                }}
              >
                {c.factId}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  color: 'var(--color-ink-3)',
                  letterSpacing: '0.06em',
                }}
              >
                {c.predicate}
              </span>
              <span style={{ fontSize: 13, color: 'var(--color-ink-2)', lineHeight: 1.4 }}>
                {c.contribution}
              </span>
            </div>
          ))}
        </div>
      )}

      <div
        style={{
          fontStyle: 'italic',
          fontSize: 12,
          color: 'var(--color-ink-3)',
          lineHeight: 1.5,
          marginTop: 2,
        }}
      >
        {insight.synthesisTestRationale}
      </div>
    </li>
  );
}

// ── Rejected disclosure ────────────────────────────────────────────

function RejectedDisclosure({ rejected }: { rejected: RejectedInsight[] }) {
  if (rejected.length === 0) {
    return (
      <section>
        <SectionLabel>Rejected candidates</SectionLabel>
        <div style={{ fontStyle: 'italic', color: 'var(--color-ink-3)', fontSize: 13 }}>
          No rejected candidates this engagement.
        </div>
      </section>
    );
  }
  return (
    <details
      data-rejected
      style={{
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-line)',
        padding: '10px 14px',
      }}
    >
      <summary
        style={{
          cursor: 'pointer',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--color-amber)',
          fontWeight: 600,
        }}
      >
        Rejected candidates · {rejected.length} (audit artifact)
      </summary>
      <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rejected.map((r) => (
          <li
            key={r.id}
            data-rejected-id={r.id}
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              borderLeft: '2px solid var(--color-amber)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 14,
                color: 'var(--color-ink)',
                lineHeight: 1.4,
                marginBottom: 6,
              }}
            >
              {r.candidateStatement}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--color-amber)',
                lineHeight: 1.5,
                letterSpacing: '0.02em',
              }}
            >
              {r.rejectionReason}
            </div>
            {r.derivedFrom && r.derivedFrom.length > 0 && (
              <div
                style={{
                  marginTop: 6,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  color: 'var(--color-ink-3)',
                }}
              >
                {r.derivedFrom.length} citation{r.derivedFrom.length === 1 ? '' : 's'} attempted
              </div>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

// ── Main component ────────────────────────────────────────────────

export function SynthesisPage(props: SynthesisPageProps) {
  const { scope, insights, rejectedInsights, onOpenFact, onMarkComplete } = props;
  const [activeFrames, setActiveFrames] = useState<Set<StrategicFrame>>(new Set());

  const toggleFrame = (f: StrategicFrame) => {
    setActiveFrames((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  };

  const visible = activeFrames.size === 0
    ? insights
    : insights.filter((i) => activeFrames.has(i.strategicFrame));

  const total = insights.length + rejectedInsights.length;
  const passRate = total === 0 ? 0 : Math.round((insights.length / total) * 100);

  return (
    <main
      role="main"
      aria-label="Synthesis"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
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
          Stage 04 · Synthesis
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
            Insights
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
            <strong style={{ color: 'var(--color-ink)' }}>{insights.length} insights</strong>
            {' · '}
            <span style={{ color: 'var(--color-amber)' }}>
              {rejectedInsights.length} rejected
            </span>
            {' · '}
            <strong style={{ color: 'var(--color-accent)' }}>{passRate}%</strong>{' '}
            pass-rate
          </span>
        </div>
      </header>

      {/* Frame filter */}
      <section>
        <SectionLabel>Filter by strategic frame</SectionLabel>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {FRAMES.map((f) => {
            const isOn = activeFrames.has(f);
            const t = frameTone(f);
            return (
              <button
                type="button"
                key={f}
                data-frame={f}
                aria-pressed={isOn}
                onClick={() => toggleFrame(f)}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  padding: '5px 12px',
                  background: isOn ? t.bg : 'transparent',
                  color: isOn ? t.fg : 'var(--color-ink-3)',
                  border: `1px solid ${isOn ? t.border : 'var(--color-line-2)'}`,
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                {f}
              </button>
            );
          })}
          {activeFrames.size > 0 && (
            <button
              type="button"
              onClick={() => setActiveFrames(new Set())}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '0.12em',
                color: 'var(--color-ink-3)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '5px 6px',
              }}
            >
              clear filter ×
            </button>
          )}
        </div>
      </section>

      {/* Insights list */}
      <section>
        <SectionLabel>
          Insights {activeFrames.size > 0 ? `· ${visible.length} of ${insights.length}` : `· ${insights.length}`}
        </SectionLabel>
        {visible.length === 0 ? (
          <div
            style={{
              padding: 18,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              fontSize: 13,
            }}
          >
            {insights.length === 0
              ? 'No insights yet — return to Dossier and run synthesis on the facts assembled there.'
              : 'No insights match the active frame filter.'}
          </div>
        ) : (
          <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {visible.map((i) => (
              <InsightCard key={i.id} insight={i} onOpenFact={onOpenFact} />
            ))}
          </ul>
        )}
      </section>

      {/* Rejected disclosure */}
      <RejectedDisclosure rejected={rejectedInsights} />

      {/* Footer */}
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
    </main>
  );
}
