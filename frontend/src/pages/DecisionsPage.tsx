/**
 * F12 — DecisionsPage: closes the engagement lifecycle.
 *
 * The output artifact: committed-decisions ledger, intelligence gap log
 * (final disposition), and the 3-session facilitator guide. Export
 * always enabled; Close engagement gated on no pending gaps.
 *
 * Stage 07 of the lifecycle (shares with WarRoom; the "war + decisions"
 * stage in the v7 7-stage spec). In a routing layer F11 and F12 may be
 * tabs of the same stage or sequenced pages.
 *
 * Headless. Theme-aware.
 */
import { ReactNode } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export type DecisionDisposition = 'committed' | 'contingent' | 'parked';
export type GapDisposition = 'primary_research' | 'accept_uncertainty' | 'descope' | 'pending';

export interface CommittedDecision {
  id: string;
  statement: string;
  owner: string;
  timing: string;
  scenarioId: string;
  scenarioName: string;
  evidenceChain: { factId: string; predicate: string }[];
  disposition: DecisionDisposition;
  rationale: string;
}

export interface GapLogEntry {
  id: string;
  importance: 'critical' | 'high' | 'medium';
  question: string;
  disposition: GapDisposition;
  remediationNote?: string;
}

export interface FacilitatorSession {
  id: 'think_like_competitor' | 'prioritise_implications' | 'risk_mitigation';
  title: string;
  duration: string;
  agenda: string[];
  outputs: string[];
  escalationTriggers?: string[];
}

export interface DecisionsPageProps {
  scope: { engagementName: string; focalAsset: string };
  decisions: CommittedDecision[];
  gaps: GapLogEntry[];
  sessions: FacilitatorSession[];
  onOpenFact: (factId: string) => void;
  onExportArtifact: () => void;
  onCloseEngagement: () => void;
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

function decisionTone(d: DecisionDisposition) {
  switch (d) {
    case 'committed':   return { fg: 'var(--color-green, #15803d)', bg: 'var(--color-green-soft, rgba(21,128,61,0.06))', border: 'var(--color-green, #15803d)' };
    case 'contingent':  return { fg: 'var(--color-amber)',           bg: 'var(--color-amber-soft, rgba(180,83,9,0.06))', border: 'var(--color-amber)' };
    case 'parked':      return { fg: 'var(--color-ink-3)',           bg: 'var(--color-surface-2)',                        border: 'var(--color-line-2)' };
  }
}

function gapTone(d: GapDisposition) {
  switch (d) {
    case 'primary_research':   return 'var(--color-accent)';
    case 'accept_uncertainty': return 'var(--color-ink-3)';
    case 'descope':            return 'var(--color-ink-4)';
    case 'pending':            return 'var(--color-red, #b91c1c)';
  }
}

const GAP_LABEL: Record<GapDisposition, string> = {
  primary_research:   'Primary research',
  accept_uncertainty: 'Accept uncertainty',
  descope:            'Descope',
  pending:            'Pending',
};

// ── Header ─────────────────────────────────────────────────────────

function DecisionsHeader({
  scope,
  decisions,
}: {
  scope: { engagementName: string; focalAsset: string };
  decisions: CommittedDecision[];
}) {
  const committed   = decisions.filter((d) => d.disposition === 'committed').length;
  const contingent  = decisions.filter((d) => d.disposition === 'contingent').length;
  const parked      = decisions.filter((d) => d.disposition === 'parked').length;
  return (
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
        Stage 07 · Decisions
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
          Engagement output.
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
          <strong style={{ color: 'var(--color-green, #15803d)' }}>{committed} committed</strong>
          {' · '}
          <strong style={{ color: 'var(--color-amber)' }}>{contingent} contingent</strong>
          {' · '}
          <strong style={{ color: 'var(--color-ink-3)' }}>{parked} parked</strong>
        </span>
      </div>
    </header>
  );
}

// ── Decision row ───────────────────────────────────────────────────

function DecisionRow({
  decision,
  onOpenFact,
}: {
  decision: CommittedDecision;
  onOpenFact: (id: string) => void;
}) {
  const t = decisionTone(decision.disposition);
  return (
    <li
      data-decision-id={decision.id}
      data-disposition={decision.disposition}
      style={{
        padding: '14px 16px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${t.border}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span
          style={{
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
          {decision.disposition}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {decision.scenarioName}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
          }}
        >
          {decision.owner} · {decision.timing}
        </span>
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
        {decision.statement}
      </div>

      <div style={{ fontSize: 12.5, color: 'var(--color-ink-3)', fontStyle: 'italic', lineHeight: 1.5 }}>
        {decision.rationale}
      </div>

      {decision.evidenceChain.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingTop: 4 }}>
          {decision.evidenceChain.map((e) => (
            <button
              type="button"
              key={e.factId}
              data-fact-id={e.factId}
              onClick={() => onOpenFact(e.factId)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                color: 'var(--color-accent)',
                background: 'var(--color-accent-soft)',
                border: '1px solid var(--color-accent)',
                padding: '2px 7px',
                cursor: 'pointer',
                letterSpacing: '0.04em',
              }}
            >
              {e.factId} · {e.predicate}
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

// ── Gap row ────────────────────────────────────────────────────────

function GapRow({ gap }: { gap: GapLogEntry }) {
  const isPending = gap.disposition === 'pending';
  return (
    <li
      data-gap-id={gap.id}
      data-pending={isPending || undefined}
      style={{
        padding: '10px 14px',
        background: isPending ? 'rgba(185,28,28,0.06)' : 'var(--color-surface)',
        border: `1px solid ${isPending ? 'var(--color-red, #b91c1c)' : 'var(--color-line)'}`,
        borderLeft: `3px solid ${gapTone(gap.disposition)}`,
        display: 'grid',
        gridTemplateColumns: '90px 1fr 180px',
        gap: 12,
        alignItems: 'baseline',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9.5,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: 'var(--color-ink-3)',
          fontWeight: 600,
        }}
      >
        {gap.importance}
      </span>
      <div>
        <div style={{ fontSize: 13.5, color: 'var(--color-ink)', lineHeight: 1.4 }}>
          {gap.question}
        </div>
        {gap.remediationNote && (
          <div style={{ fontSize: 11.5, color: 'var(--color-ink-3)', fontStyle: 'italic', marginTop: 2 }}>
            {gap.remediationNote}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: gapTone(gap.disposition),
          fontWeight: 600,
          textAlign: 'right',
        }}
      >
        {GAP_LABEL[gap.disposition]}
      </span>
    </li>
  );
}

// ── Session card ───────────────────────────────────────────────────

function SessionCard({ session }: { session: FacilitatorSession }) {
  const labelId = `session-${session.id}`;
  return (
    <section
      data-session={session.id}
      aria-labelledby={labelId}
      style={{
        padding: '14px 16px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderTop: '3px solid var(--color-accent)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <header style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
        <h3
          id={labelId}
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 16,
            fontWeight: 500,
            color: 'var(--color-ink)',
            margin: 0,
          }}
        >
          {session.title}
        </h3>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--color-accent)',
            fontWeight: 600,
          }}
        >
          {session.duration}
        </span>
      </header>

      <div>
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
          Agenda
        </div>
        <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-2)' }}>
          {session.agenda.map((a, i) => (
            <li key={i} style={{ fontSize: 12.5, marginBottom: 3, lineHeight: 1.45 }}>
              {a}
            </li>
          ))}
        </ul>
      </div>

      <div>
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
          Outputs
        </div>
        <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-2)' }}>
          {session.outputs.map((o, i) => (
            <li key={i} style={{ fontSize: 12.5, marginBottom: 3, lineHeight: 1.45 }}>
              {o}
            </li>
          ))}
        </ul>
      </div>

      {session.escalationTriggers && session.escalationTriggers.length > 0 && (
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9.5,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: 'var(--color-amber)',
              marginBottom: 4,
            }}
          >
            Escalation triggers
          </div>
          <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-2)' }}>
            {session.escalationTriggers.map((t, i) => (
              <li key={i} style={{ fontSize: 12.5, marginBottom: 3, lineHeight: 1.45, fontStyle: 'italic' }}>
                {t}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// ── Main component ────────────────────────────────────────────────

export function DecisionsPage(props: DecisionsPageProps) {
  const { scope, decisions, gaps, sessions, onOpenFact, onExportArtifact, onCloseEngagement } = props;
  const anyPending = gaps.some((g) => g.disposition === 'pending');

  // Group decisions by disposition order: committed first, then contingent, then parked
  const committed   = decisions.filter((d) => d.disposition === 'committed');
  const contingent  = decisions.filter((d) => d.disposition === 'contingent');
  const parked      = decisions.filter((d) => d.disposition === 'parked');

  return (
    <main
      role="main"
      aria-label="Decisions"
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
      <DecisionsHeader scope={scope} decisions={decisions} />

      {/* Decision ledger */}
      <section>
        <SectionLabel>Decision ledger · {decisions.length}</SectionLabel>
        {decisions.length === 0 ? (
          <div
            style={{
              padding: 18,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              fontSize: 13,
            }}
          >
            No decisions committed yet. Play scenarios in the War Room to produce defensible decisions.
          </div>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[...committed, ...contingent, ...parked].map((d) => (
              <DecisionRow key={d.id} decision={d} onOpenFact={onOpenFact} />
            ))}
          </ul>
        )}
      </section>

      {/* Gap log */}
      <section>
        <SectionLabel>
          Intelligence gap log · {gaps.length}
          {anyPending && (
            <span style={{ color: 'var(--color-red, #b91c1c)', marginLeft: 8, fontWeight: 600 }}>
              · resolve pending before close
            </span>
          )}
        </SectionLabel>
        {gaps.length === 0 ? (
          <div
            style={{
              padding: 14,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              fontSize: 13,
            }}
          >
            No gaps recorded for this engagement.
          </div>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {gaps.map((g) => (
              <GapRow key={g.id} gap={g} />
            ))}
          </ul>
        )}
      </section>

      {/* Facilitator guide */}
      <section>
        <SectionLabel>Facilitator guide · next workshop · 3 sessions</SectionLabel>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12,
          }}
        >
          {sessions.map((s) => (
            <SessionCard key={s.id} session={s} />
          ))}
        </div>
      </section>

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
          onClick={onExportArtifact}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            padding: '8px 16px',
            background: 'transparent',
            color: 'var(--color-ink-2)',
            border: '1px solid var(--color-line-2)',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          Export PDF + JSON →
        </button>
        <button
          type="button"
          aria-label="Close engagement"
          onClick={!anyPending ? onCloseEngagement : undefined}
          disabled={anyPending}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            padding: '8px 16px',
            background: anyPending ? 'var(--color-surface-2)' : 'var(--color-accent)',
            color: anyPending ? 'var(--color-ink-3)' : 'var(--color-surface)',
            border: `1px solid ${anyPending ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
            cursor: anyPending ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {anyPending ? 'Resolve pending gaps first' : 'Close engagement ✓'}
        </button>
      </footer>
    </main>
  );
}
