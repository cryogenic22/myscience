/**
 * F10 — ScenariosPage: event-triggered scenarios with team-moves and
 * decision-options.
 *
 * Stage 6 of the engagement lifecycle. Replaces v7's trend-described
 * narratives with the ZS framework's typed chain:
 *   trigger event → team moves → decision options → decision output.
 *
 * Each scenario has its own blocked-by-gaps state — a scenario depending
 * on unresolved gaps cannot run in the War Room, and the workshop CTA
 * stays locked until all scenarios are unblocked.
 *
 * Probability dial shows prior + current — the learn-loop in operation.
 *
 * Headless. Theme-aware.
 */
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { scenariosApi, type CalibrationStep } from '../api';

// ── Types ──────────────────────────────────────────────────────────

export interface ScenarioEvidence {
  factId: string;
  predicate: string;
}

export interface TeamMove {
  team: string;
  move: string;
  rationale: string;
  /** PB-H11: illustrative directional impact per team, in [-1, 1]. */
  impact?: Record<string, number>;
}

export interface DecisionOption {
  id: string;
  statement: string;
  rationale: string;
  npv5yDkkBn?: number;
  recommended?: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  trigger: {
    event: string;
    date?: string;
    evidence: ScenarioEvidence[];
  };
  probability: number;          // 0..1
  probabilityCurrent?: number;  // 0..1, only set after calibration
  calibrationNote?: string | null;  // PB-H14 — why current moved (cites the signal)
  teamMoves: TeamMove[];
  decisionOptions: DecisionOption[];
  decisionOutput?: string;
  blockedByGaps?: string[];
}

export interface ScenariosPageProps {
  eid: string;
  scope: { engagementName: string; focalAsset: string };
  scenarios: Scenario[];
  activeScenarioId: string | null;
  onSelectScenario: (id: string | null) => void;
  onPlayScenario: (id: string) => void;
  onOpenFact: (factId: string) => void;
  onMarkComplete: () => void;
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

function ProbabilityDial({ prior, current }: { prior: number; current?: number }) {
  const priorPct = Math.round(prior * 100);
  const currentPct = current !== undefined ? Math.round(current * 100) : null;
  const delta = currentPct !== null ? currentPct - priorPct : 0;
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        gap: 6,
        fontFamily: 'var(--font-mono)',
        fontSize: 14,
        fontWeight: 600,
        color: 'var(--color-ink)',
      }}
    >
      <span style={{ color: currentPct !== null ? 'var(--color-ink-3)' : 'var(--color-ink)' }}>
        {priorPct}%
      </span>
      {currentPct !== null && (
        <>
          <span style={{ fontSize: 11, color: 'var(--color-ink-4)' }}>→</span>
          <span style={{ color: delta >= 0 ? 'var(--color-accent)' : 'var(--color-ink-2)' }}>
            {currentPct}%
          </span>
        </>
      )}
    </div>
  );
}

// ── Probability history timeline (FS-1 / OQ2) ──────────────────────
// The append-only audit tape: how this scenario's probability moved and why.
// Lazy — only mounted when a card is expanded, so it fetches on demand.

function ProbabilityTimeline({ eid, scenarioId }: { eid: string; scenarioId: string }) {
  const [steps, setSteps] = useState<CalibrationStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    scenariosApi
      .probabilityHistory(eid, scenarioId)
      .then((r) => { if (!cancelled) setSteps(r.history); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); });
    return () => { cancelled = true; };
  }, [eid, scenarioId]);

  if (error) return null; // non-blocking: a history failure never breaks the card
  if (steps === null) return null; // loading — stay quiet until we have data

  if (steps.length === 0) {
    return (
      <section data-testid="probability-timeline-empty">
        <SectionLabel>Probability history</SectionLabel>
        <div style={{ fontSize: 11.5, color: 'var(--color-ink-3)', lineHeight: 1.45 }}>
          No calibration yet — probability still at its structural prior.
        </div>
      </section>
    );
  }

  return (
    <section data-testid="probability-timeline">
      <SectionLabel>Probability history</SectionLabel>
      <ol
        style={{
          listStyle: 'none', margin: 0, padding: 0,
          display: 'flex', flexDirection: 'column', gap: 6,
        }}
      >
        {steps.map((s) => {
          const down = s.delta < 0;
          const pct = (n: number | null) => (n === null ? '—' : `${Math.round(n * 100)}%`);
          const date = (s.createdAt || '').slice(0, 10);
          return (
            <li
              key={s.id}
              data-testid="calibration-step"
              data-direction={down ? 'down' : 'up'}
              title={s.note || undefined}
              style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 11.5 }}
            >
              <span
                aria-hidden
                style={{ color: down ? 'var(--color-amber)' : 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
              >
                {down ? '▼' : '▲'}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ink-2)' }}>
                {pct(s.prevProb)} → {pct(s.newProb)}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: down ? 'var(--color-amber)' : 'var(--color-accent)' }}>
                ({s.delta >= 0 ? '+' : ''}{Math.round(s.delta * 100)})
              </span>
              <span style={{ color: 'var(--color-ink-3)', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>
                {s.nSupporting > 0 && `${s.nSupporting} support`}
                {s.nContradicting > 0 && `${s.nSupporting > 0 ? ' · ' : ''}${s.nContradicting} contradict`}
              </span>
              {date && (
                <span style={{ marginLeft: 'auto', color: 'var(--color-ink-4)', fontFamily: 'var(--font-mono)', fontSize: 10.5 }}>
                  {date}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

// ── Scenario card (collapsed) ──────────────────────────────────────

function ScenarioCard({
  scenario,
  eid,
  active,
  onSelect,
  onPlay,
  onOpenFact,
}: {
  scenario: Scenario;
  eid: string;
  active: boolean;
  onSelect: (id: string | null) => void;
  onPlay: (id: string) => void;
  onOpenFact: (factId: string) => void;
}) {
  const blocked = (scenario.blockedByGaps?.length ?? 0) > 0;

  return (
    <li
      data-scenario-id={scenario.id}
      data-expanded={active || undefined}
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-line)'}`,
        borderLeft: `3px solid ${blocked ? 'var(--color-amber)' : 'var(--color-accent)'}`,
        opacity: blocked ? 0.85 : 1,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Card header (always visible) */}
      <div
        data-card-header
        role="button"
        tabIndex={0}
        onClick={() => onSelect(active ? null : scenario.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') onSelect(active ? null : scenario.id);
        }}
        style={{
          padding: '14px 16px',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <h3
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18,
              fontWeight: 500,
              color: 'var(--color-ink)',
              margin: 0,
            }}
          >
            {scenario.name}
          </h3>
          <ProbabilityDial prior={scenario.probability} current={scenario.probabilityCurrent} />
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
            }}
          >
            {scenario.teamMoves.length} team moves · {scenario.decisionOptions.length} options
          </span>
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--color-ink-2)', lineHeight: 1.5 }}>
          {scenario.trigger.event}
          {scenario.trigger.date && (
            <span
              style={{
                marginLeft: 8,
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                color: 'var(--color-ink-3)',
                letterSpacing: '0.04em',
              }}
            >
              · {scenario.trigger.date}
            </span>
          )}
        </div>
        {blocked && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              color: 'var(--color-amber)',
              letterSpacing: '0.04em',
            }}
          >
            ◇ Blocked by unresolved gap{scenario.blockedByGaps!.length === 1 ? '' : 's'}: {scenario.blockedByGaps!.join(', ')}
          </div>
        )}
        {scenario.calibrationNote && (
          <div
            data-testid="scenario-calibration-note"
            style={{
              fontSize: 11.5,
              color: 'var(--color-ink-3)',
              lineHeight: 1.45,
              borderLeft: '2px solid var(--color-accent)',
              paddingLeft: 8,
            }}
            title="How this scenario's probability was re-weighted from new signals (PB-H14)"
          >
            {scenario.calibrationNote}
          </div>
        )}
      </div>

      {/* Expanded detail */}
      {active && (
        <div
          style={{
            padding: '0 16px 16px',
            borderTop: '1px dashed var(--color-line-soft, var(--color-line))',
            display: 'flex',
            flexDirection: 'column',
            gap: 18,
          }}
        >
          {/* Probability history (FS-1 / OQ2) */}
          <div style={{ paddingTop: 14 }}>
            <ProbabilityTimeline eid={eid} scenarioId={scenario.id} />
          </div>

          {/* Trigger evidence */}
          <section>
            <SectionLabel>Trigger evidence</SectionLabel>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {scenario.trigger.evidence.map((e) => (
                <button
                  type="button"
                  key={e.factId}
                  data-fact-id={e.factId}
                  onClick={() => onOpenFact(e.factId)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--color-accent)',
                    background: 'var(--color-accent-soft)',
                    border: '1px solid var(--color-accent)',
                    padding: '3px 8px',
                    cursor: 'pointer',
                    letterSpacing: '0.04em',
                  }}
                >
                  {e.factId} · {e.predicate}
                </button>
              ))}
            </div>
          </section>

          {/* Team moves */}
          <section>
            <SectionLabel>Team moves · derived from rational interest</SectionLabel>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {scenario.teamMoves.map((m, i) => (
                <li
                  key={i}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '100px 1fr',
                    gap: 12,
                    padding: '8px 10px',
                    background: 'var(--color-surface-2)',
                    borderLeft: '2px solid var(--color-teal, var(--color-accent))',
                  }}
                >
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--color-teal, var(--color-accent))',
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      fontWeight: 600,
                    }}
                  >
                    {m.team}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: 13.5,
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                        marginBottom: 3,
                      }}
                    >
                      {m.move}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-ink-3)', lineHeight: 1.5 }}>
                      {m.rationale}
                    </div>
                    {m.impact && Object.keys(m.impact).length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }} title="Illustrative directional impact (structural estimate, not a forecast)">
                        {Object.entries(m.impact).map(([team, delta]) => {
                          const pos = delta >= 0;
                          return (
                            <span
                              key={team}
                              data-impact-team={team}
                              style={{
                                fontFamily: 'var(--font-mono)',
                                fontSize: 10,
                                letterSpacing: '0.02em',
                                padding: '1px 6px',
                                borderRadius: 'var(--radius-pill)',
                                background: pos ? 'var(--color-green-soft, rgba(21,128,61,0.08))' : 'rgba(185,28,28,0.08)',
                                color: pos ? 'var(--color-green, #15803d)' : 'var(--color-red, #b91c1c)',
                                border: `1px solid ${pos ? 'var(--color-green, #15803d)' : 'var(--color-red, #b91c1c)'}`,
                              }}
                            >
                              {team} {pos ? '+' : ''}{delta.toFixed(1)}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Decision options */}
          <section>
            <SectionLabel>Decision options · mutually exclusive paths</SectionLabel>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 8,
              }}
            >
              {scenario.decisionOptions.map((o) => (
                <div
                  key={o.id}
                  data-option-id={o.id}
                  data-recommended={o.recommended || undefined}
                  style={{
                    padding: '12px 14px',
                    background: 'var(--color-surface)',
                    border: `1px solid ${o.recommended ? 'var(--color-accent)' : 'var(--color-line)'}`,
                    borderLeft: `3px solid ${o.recommended ? 'var(--color-accent)' : 'var(--color-line-2)'}`,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  {o.recommended && (
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 9.5,
                        letterSpacing: '0.18em',
                        textTransform: 'uppercase',
                        color: 'var(--color-accent)',
                        fontWeight: 600,
                      }}
                    >
                      ★ Recommended
                    </span>
                  )}
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: 14,
                      fontWeight: 500,
                      color: 'var(--color-ink)',
                      lineHeight: 1.3,
                    }}
                  >
                    {o.statement}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-ink-3)', lineHeight: 1.45 }}>
                    {o.rationale}
                  </div>
                  {o.npv5yDkkBn !== undefined && (
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: o.recommended ? 'var(--color-accent)' : 'var(--color-ink-2)',
                        letterSpacing: '0.04em',
                        marginTop: 4,
                      }}
                    >
                      5y NPV: <strong style={{ color: 'var(--color-ink)' }}>{o.npv5yDkkBn.toFixed(1)} bn DKK</strong>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Decision output */}
          {scenario.decisionOutput && (
            <section>
              <SectionLabel>Wargame surfaces</SectionLabel>
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-accent-soft)',
                  borderLeft: '3px solid var(--color-accent)',
                  fontFamily: 'var(--font-display)',
                  fontSize: 14.5,
                  color: 'var(--color-ink)',
                  lineHeight: 1.5,
                  fontStyle: 'italic',
                }}
              >
                {scenario.decisionOutput}
              </div>
            </section>
          )}

          {/* Play CTA */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={() => !blocked && onPlay(scenario.id)}
              disabled={blocked}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                padding: '8px 16px',
                background: blocked ? 'var(--color-surface-2)' : 'var(--color-accent)',
                color: blocked ? 'var(--color-ink-3)' : 'var(--color-surface)',
                border: `1px solid ${blocked ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
                cursor: blocked ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              Play in War Room →
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

// ── Main component ────────────────────────────────────────────────

export function ScenariosPage(props: ScenariosPageProps) {
  const { eid, scope, scenarios, activeScenarioId, onSelectScenario,
          onPlayScenario, onOpenFact, onMarkComplete } = props;

  const sorted = [...scenarios].sort((a, b) => b.probability - a.probability);
  const recommendedCount = scenarios.filter((s) => s.decisionOutput).length;
  const anyBlocked = scenarios.some((s) => (s.blockedByGaps?.length ?? 0) > 0);

  return (
    <main
      role="main"
      aria-label="Scenarios"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
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
          Stage 06 · Scenarios
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
            Event-triggered scenarios.
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
            <strong style={{ color: 'var(--color-ink)' }}>{scenarios.length} scenarios</strong>
            {' · '}
            <strong style={{ color: 'var(--color-accent)' }}>{recommendedCount} recommended</strong>
          </span>
        </div>
      </header>

      <section>
        <SectionLabel>Scenarios · sorted by probability</SectionLabel>
        {sorted.length === 0 ? (
          <div
            style={{
              padding: 20,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              textAlign: 'center',
            }}
          >
            No scenarios yet — return to Synthesis to derive event-triggered scenarios from insights.
          </div>
        ) : (
          <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {sorted.map((s) => (
              <ScenarioCard
                key={s.id}
                scenario={s}
                eid={eid}
                active={s.id === activeScenarioId}
                onSelect={onSelectScenario}
                onPlay={onPlayScenario}
                onOpenFact={onOpenFact}
              />
            ))}
          </ul>
        )}
      </section>

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
          aria-label="Mark stage complete"
          onClick={!anyBlocked ? onMarkComplete : undefined}
          disabled={anyBlocked}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            padding: '8px 16px',
            background: anyBlocked ? 'var(--color-surface-2)' : 'var(--color-accent)',
            color: anyBlocked ? 'var(--color-ink-3)' : 'var(--color-surface)',
            border: `1px solid ${anyBlocked ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
            cursor: anyBlocked ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {anyBlocked ? 'Resolve blocked scenarios first' : 'Mark stage complete →'}
        </button>
      </footer>
    </main>
  );
}
