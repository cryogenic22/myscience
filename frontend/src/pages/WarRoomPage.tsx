/**
 * F11 — WarRoomPage: the three-mode toggle (Guided / Autonomous / Game-
 * theoretic) over one shared Scenario state.
 *
 * The largest single surface in the v7 IA. Each mode is a first-class
 * surface, not a re-skin — Guided is a real move composer + counter-move
 * projection panel; Autonomous is a controlled simulation runner with
 * narration stream; Game-theoretic is a payoff matrix with the Nash
 * equilibrium cell highlighted and an optional Monte Carlo summary.
 *
 * Mode-shift made visible: the root carries `data-warroom="active"` which
 * the ZS theme uses to swap `--color-accent` to the deep teal (#0F5D6A).
 * You see the colour shift the moment you enter the simulation.
 *
 * Headless. Theme-aware.
 */
import { ReactNode } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export type WarRoomMode = 'guided' | 'autonomous' | 'game_theoretic';

export interface ScenarioContext {
  id: string;
  name: string;
  trigger: { event: string; date?: string };
}

export interface NovoMove {
  id: string;
  type: string;
  statement: string;
}

export interface LedgerEntry {
  team: string;
  move: string;
  round: number;
  rationale: string;
}

export interface ProjectedCounterMove {
  team: string;
  move: string;
  confidence: number; // 0..1
  rationale: string;
}

export type AutonomousState = 'idle' | 'running' | 'paused' | 'complete';

export interface PayoffMatrix {
  rowsLabel: string;
  colsLabel: string;
  rows: string[];
  cols: string[];
  cells: number[][];
  nash: [number, number];
}

export interface MonteCarloSummary {
  runs: number;
  meanNovoNPV: number;
  p10: number;
  p90: number;
}

export interface WarRoomPageProps {
  scope: { engagementName: string; focalAsset: string };
  scenario: ScenarioContext;
  mode: WarRoomMode;
  onModeChange: (m: WarRoomMode) => void;
  onMarkComplete: () => void;

  // Guided
  guidedRound: number;
  availableNovoMoves: NovoMove[];
  guidedLedger: LedgerEntry[];
  projectedCounterMoves: ProjectedCounterMove[];
  onPlayMove: (moveId: string) => void;
  onCommitTurn: () => void;

  // Autonomous
  autonomousState: AutonomousState;
  autonomousNarration: string[];
  onAutonomousStart: () => void;
  onAutonomousStep: () => void;
  onAutonomousPause: () => void;
  onAutonomousReset: () => void;

  // Game-theoretic
  payoffMatrix: PayoffMatrix;
  monteCarlo?: MonteCarloSummary;
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

const MODE_LABEL: Record<WarRoomMode, string> = {
  guided:         'Guided',
  autonomous:     'Autonomous',
  game_theoretic: 'Game-theoretic',
};

const MODE_PANEL_ID: Record<WarRoomMode, string> = {
  guided:         'panel-guided',
  autonomous:     'panel-autonomous',
  game_theoretic: 'panel-game-theoretic',
};

const MODE_TAB_ID: Record<WarRoomMode, string> = {
  guided:         'tab-guided',
  autonomous:     'tab-autonomous',
  game_theoretic: 'tab-game-theoretic',
};

// ── Header ─────────────────────────────────────────────────────────

function WarRoomHeader({
  scope,
  scenario,
}: {
  scope: { engagementName: string; focalAsset: string };
  scenario: ScenarioContext;
}) {
  return (
    <header
      style={{
        padding: '20px 28px 16px',
        background: 'var(--color-surface)',
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
          marginBottom: 6,
        }}
      >
        Stage 07 · War Room
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 28,
            fontWeight: 400,
            color: 'var(--color-ink)',
            letterSpacing: '-0.012em',
            margin: 0,
          }}
        >
          {scenario.name}
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
      </div>
      <div
        style={{
          marginTop: 8,
          fontSize: 13.5,
          color: 'var(--color-ink-2)',
          lineHeight: 1.5,
          fontStyle: 'italic',
        }}
      >
        Trigger: {scenario.trigger.event}
        {scenario.trigger.date && (
          <span
            style={{
              marginLeft: 6,
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
              fontStyle: 'normal',
            }}
          >
            · {scenario.trigger.date}
          </span>
        )}
      </div>
    </header>
  );
}

// ── Mode tablist ───────────────────────────────────────────────────

function ModeTablist({
  mode,
  onModeChange,
}: {
  mode: WarRoomMode;
  onModeChange: (m: WarRoomMode) => void;
}) {
  const modes: WarRoomMode[] = ['guided', 'autonomous', 'game_theoretic'];
  return (
    <div
      role="tablist"
      aria-label="War Room mode"
      style={{
        display: 'flex',
        gap: 0,
        background: 'var(--color-surface-2)',
        borderBottom: '1px solid var(--color-divider)',
        padding: '0 24px',
      }}
    >
      {modes.map((m) => {
        const active = m === mode;
        return (
          <button
            type="button"
            key={m}
            id={MODE_TAB_ID[m]}
            role="tab"
            data-mode={m}
            aria-selected={active}
            aria-controls={MODE_PANEL_ID[m]}
            tabIndex={active ? 0 : -1}
            onClick={() => onModeChange(m)}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              padding: '14px 18px',
              background: 'transparent',
              color: active ? 'var(--color-accent)' : 'var(--color-ink-3)',
              border: 'none',
              borderBottom: `2px solid ${active ? 'var(--color-accent)' : 'transparent'}`,
              cursor: 'pointer',
              fontWeight: active ? 600 : 500,
            }}
          >
            {MODE_LABEL[m]}
          </button>
        );
      })}
    </div>
  );
}

// ── Guided panel ───────────────────────────────────────────────────

function GuidedPanel({
  round,
  moves,
  ledger,
  counters,
  onPlayMove,
  onCommitTurn,
}: {
  round: number;
  moves: NovoMove[];
  ledger: LedgerEntry[];
  counters: ProjectedCounterMove[];
  onPlayMove: (id: string) => void;
  onCommitTurn: () => void;
}) {
  return (
    <div
      id={MODE_PANEL_ID.guided}
      role="tabpanel"
      aria-labelledby={MODE_TAB_ID.guided}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 24,
        padding: '24px 28px',
      }}
    >
      {/* Left column: round + available moves + ledger */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-accent)',
            fontWeight: 600,
          }}
        >
          Round {round}
        </div>

        <section>
          <SectionLabel>Available Novo moves · click to play</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {moves.map((m) => (
              <button
                type="button"
                key={m.id}
                data-move-id={m.id}
                onClick={() => onPlayMove(m.id)}
                style={{
                  padding: '10px 14px',
                  textAlign: 'left',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-line)',
                  borderLeft: '3px solid var(--color-accent)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9.5,
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                    color: 'var(--color-ink-3)',
                  }}
                >
                  {m.type}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 13.5,
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                    lineHeight: 1.3,
                  }}
                >
                  {m.statement}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <SectionLabel>Move ledger · {ledger.length}</SectionLabel>
          {ledger.length === 0 ? (
            <div
              style={{
                padding: 14,
                border: '1px dashed var(--color-line-2)',
                color: 'var(--color-ink-3)',
                fontStyle: 'italic',
                fontSize: 13,
              }}
            >
              Pick a move to begin Round 1. The ledger captures every move + rationale for the corporate-memory artifact.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {ledger.map((e, i) => (
                <li
                  key={i}
                  data-ledger-row
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '60px 80px 1fr',
                    gap: 10,
                    padding: '8px 12px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-line)',
                  }}
                >
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10.5,
                      color: 'var(--color-ink-3)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    R{e.round}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10.5,
                      color: 'var(--color-accent)',
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      fontWeight: 600,
                    }}
                  >
                    {e.team}
                  </span>
                  <div>
                    <div style={{ fontSize: 13, color: 'var(--color-ink)', fontWeight: 500 }}>{e.move}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--color-ink-3)', fontStyle: 'italic' }}>
                      {e.rationale}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Right column: projected counter-moves + commit */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <section>
          <SectionLabel>Projected counter-moves · agent confidence</SectionLabel>
          {counters.length === 0 ? (
            <div
              style={{
                padding: 14,
                border: '1px dashed var(--color-line-2)',
                color: 'var(--color-ink-3)',
                fontStyle: 'italic',
                fontSize: 13,
              }}
            >
              Play a move to see the other teams' projected responses.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {counters.map((c, i) => (
                <li
                  key={i}
                  style={{
                    padding: '10px 14px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-line)',
                    borderLeft: '3px solid var(--color-teal, var(--color-accent))',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10.5,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        color: 'var(--color-teal, var(--color-accent))',
                        fontWeight: 600,
                      }}
                    >
                      {c.team}
                    </span>
                    <span
                      style={{
                        marginLeft: 'auto',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--color-ink-2)',
                        letterSpacing: '0.04em',
                      }}
                    >
                      conf <strong style={{ color: 'var(--color-ink)' }}>{Math.round(c.confidence * 100)}%</strong>
                    </span>
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: 13.5,
                      fontWeight: 500,
                      color: 'var(--color-ink)',
                      marginBottom: 3,
                    }}
                  >
                    {c.move}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--color-ink-3)', fontStyle: 'italic' }}>
                    {c.rationale}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onCommitTurn}
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
            Commit turn →
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Autonomous panel ───────────────────────────────────────────────

function AutonomousPanel({
  state,
  narration,
  onStart,
  onStep,
  onPause,
  onReset,
}: {
  state: AutonomousState;
  narration: string[];
  onStart: () => void;
  onStep: () => void;
  onPause: () => void;
  onReset: () => void;
}) {
  const playEnabled = state === 'idle' || state === 'paused' || state === 'complete';
  const pauseEnabled = state === 'running';
  const stepEnabled = state === 'idle' || state === 'paused';
  const resetEnabled = state !== 'idle';

  return (
    <div
      id={MODE_PANEL_ID.autonomous}
      role="tabpanel"
      aria-labelledby={MODE_TAB_ID.autonomous}
      style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}
    >
      {/* Controls */}
      <section style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: state === 'running' ? 'var(--color-accent)' : 'var(--color-ink-3)',
            fontWeight: 600,
          }}
        >
          {state}
          {state === 'running' && <span style={{ marginLeft: 6 }}>●</span>}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {playEnabled && (
            <button
              type="button"
              onClick={onStart}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                padding: '6px 14px',
                background: 'var(--color-accent)',
                color: 'var(--color-surface)',
                border: '1px solid var(--color-accent)',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ▶ Play
            </button>
          )}
          {pauseEnabled && (
            <button
              type="button"
              onClick={onPause}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                padding: '6px 14px',
                background: 'transparent',
                color: 'var(--color-ink-2)',
                border: '1px solid var(--color-line-2)',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ❘❘ Pause
            </button>
          )}
          {stepEnabled && (
            <button
              type="button"
              onClick={onStep}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                padding: '6px 14px',
                background: 'transparent',
                color: 'var(--color-ink-2)',
                border: '1px solid var(--color-line-2)',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ▶❘ Step
            </button>
          )}
          {resetEnabled && (
            <button
              type="button"
              onClick={onReset}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                padding: '6px 14px',
                background: 'transparent',
                color: 'var(--color-ink-3)',
                border: '1px solid var(--color-line-2)',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ↻ Reset
            </button>
          )}
        </div>
      </section>

      {/* Narration */}
      <section>
        <SectionLabel>Simulation narration</SectionLabel>
        {narration.length === 0 ? (
          <div
            style={{
              padding: 24,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              fontSize: 14,
              textAlign: 'center',
            }}
          >
            Press play to begin simulation. Agents will drive Novo, Lilly, Payer, and HCP in parallel; the narration streams here as moves play.
          </div>
        ) : (
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              maxHeight: 500,
              overflow: 'auto',
            }}
          >
            {narration.map((line, i) => (
              <li
                key={i}
                style={{
                  padding: '8px 14px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  color: 'var(--color-ink-2)',
                  lineHeight: 1.6,
                  borderBottom: '1px solid var(--color-line-soft, var(--color-line))',
                }}
              >
                {line}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// ── Game-theoretic panel ───────────────────────────────────────────

function GameTheoreticPanel({
  matrix,
  mc,
}: {
  matrix: PayoffMatrix;
  mc?: MonteCarloSummary;
}) {
  return (
    <div
      id={MODE_PANEL_ID.game_theoretic}
      role="tabpanel"
      aria-labelledby={MODE_TAB_ID.game_theoretic}
      style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}
    >
      <section>
        <SectionLabel>Payoff matrix · 5y NPV (DKK bn)</SectionLabel>
        <table
          aria-label="Payoff matrix"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  padding: '10px 12px',
                  textAlign: 'left',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9.5,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: 'var(--color-ink-3)',
                }}
              >
                {matrix.rowsLabel} ↓ · {matrix.colsLabel} →
              </th>
              {matrix.cols.map((c) => (
                <th
                  key={c}
                  scope="col"
                  style={{
                    padding: '10px 12px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--color-ink-2)',
                    letterSpacing: '0.04em',
                    fontWeight: 500,
                    textAlign: 'center',
                  }}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row, ri) => (
              <tr key={row} style={{ borderTop: '1px solid var(--color-line-soft, var(--color-line))' }}>
                <th
                  scope="row"
                  style={{
                    padding: '10px 12px',
                    textAlign: 'left',
                    fontFamily: 'var(--font-display)',
                    fontSize: 13,
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                  }}
                >
                  {row}
                </th>
                {matrix.cols.map((col, ci) => {
                  const isNash = matrix.nash[0] === ri && matrix.nash[1] === ci;
                  const value = matrix.cells[ri][ci];
                  return (
                    <td
                      key={col}
                      data-payoff-cell
                      data-nash={isNash || undefined}
                      style={{
                        padding: '10px 12px',
                        textAlign: 'center',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 13,
                        color: isNash ? 'var(--color-accent)' : 'var(--color-ink-2)',
                        background: isNash ? 'var(--color-accent-soft)' : 'transparent',
                        border: isNash ? '2px solid var(--color-accent)' : '1px solid transparent',
                        fontWeight: isNash ? 700 : 500,
                      }}
                    >
                      {isNash && <span style={{ marginRight: 4 }}>★</span>}
                      {value.toFixed(1)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        <div
          style={{
            marginTop: 8,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--color-accent)',
            letterSpacing: '0.04em',
          }}
        >
          ★ Nash equilibrium · {matrix.rows[matrix.nash[0]]} × {matrix.cols[matrix.nash[1]]} →{' '}
          {matrix.cells[matrix.nash[0]][matrix.nash[1]].toFixed(1)} bn DKK
        </div>
      </section>

      {mc && (
        <section>
          <SectionLabel>Monte Carlo · 5y NPV distribution</SectionLabel>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
              gap: 8,
            }}
          >
            <div style={{ padding: 14, background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 4 }}>
                Runs
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color: 'var(--color-ink)' }}>
                {mc.runs.toLocaleString()} runs
              </div>
            </div>
            <div style={{ padding: 14, background: 'var(--color-surface)', border: '1px solid var(--color-line)', borderLeft: '3px solid var(--color-accent)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 4 }}>
                Mean Novo NPV
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color: 'var(--color-accent)' }}>
                {mc.meanNovoNPV.toFixed(1)} bn DKK
              </div>
            </div>
            <div style={{ padding: 14, background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 4 }}>
                p10 – p90
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>
                {mc.p10.toFixed(1)} – {mc.p90.toFixed(1)} bn DKK
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────

export function WarRoomPage(props: WarRoomPageProps) {
  const {
    scope, scenario, mode, onModeChange, onMarkComplete,
    guidedRound, availableNovoMoves, guidedLedger, projectedCounterMoves,
    onPlayMove, onCommitTurn,
    autonomousState, autonomousNarration,
    onAutonomousStart, onAutonomousStep, onAutonomousPause, onAutonomousReset,
    payoffMatrix, monteCarlo,
  } = props;

  return (
    <main
      role="main"
      aria-label="War Room"
      data-warroom="active"
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      <WarRoomHeader scope={scope} scenario={scenario} />
      <ModeTablist mode={mode} onModeChange={onModeChange} />

      <div style={{ flex: '1 1 auto' }}>
        {mode === 'guided' && (
          <GuidedPanel
            round={guidedRound}
            moves={availableNovoMoves}
            ledger={guidedLedger}
            counters={projectedCounterMoves}
            onPlayMove={onPlayMove}
            onCommitTurn={onCommitTurn}
          />
        )}
        {mode === 'autonomous' && (
          <AutonomousPanel
            state={autonomousState}
            narration={autonomousNarration}
            onStart={onAutonomousStart}
            onStep={onAutonomousStep}
            onPause={onAutonomousPause}
            onReset={onAutonomousReset}
          />
        )}
        {mode === 'game_theoretic' && (
          <GameTheoreticPanel matrix={payoffMatrix} mc={monteCarlo} />
        )}
      </div>

      <footer
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 12,
          padding: '16px 28px 24px',
          borderTop: '1px solid var(--color-divider)',
          background: 'var(--color-surface)',
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
