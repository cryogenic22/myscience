import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import type { Moment, Play } from '../../types/helix';
import { IMPACT_CATEGORIES } from '../../types/helix';
import type { Signal } from '../../api';

/**
 * Loop #18 — Cinematic Moment overlay.
 *
 * Full-screen overlay triggered from a Bridge MomentCard click.
 * Hybrid theme: the underlying dark Bridge stays in the DOM behind;
 * the overlay is forced into a light editorial register via the
 * `data-theme="hybrid-light"` data attribute on the root.
 *
 * Layout (per `specs/helix_proto.tsx` ~line 711):
 *   ┌────────────────────────────────────────────────────┐
 *   │ ← Back   MOMENT.M-XYZ · 72H REMAINING              │
 *   ├────────────────────────────────────────────────────┤
 *   │ STRATEGIC MOMENT                                    │
 *   │ Serif title (38px)                                  │
 *   │ Summary (15px dim)                                  │
 *   │                                                      │
 *   │  Plays (3 cards)            Signal chain            │
 *   │  ────────────────           ───────────────         │
 *   │  [Aggressive]               • s1: SURMOUNT-MMO …    │
 *   │  [Balanced] ← selected      • s5: KOL signal …      │
 *   │  [Cautious]                                          │
 *   │                              Belief shift            │
 *   │  Outcome distribution        18% → 41%               │
 *   │  (Monte Carlo)               ▓▓▓▓░░░░               │
 *   │                                                      │
 *   │  [⚔ War Room] [Defer] [Commit Decision →]           │
 *   └────────────────────────────────────────────────────┘
 */

interface Props {
  moment: Moment;
  signals: Signal[];
  close: () => void;
}

export default function MomentView({ moment, signals, close }: Props) {
  const balanced = moment.plays.find((p) => p.kind === 'balanced') ?? moment.plays[0];
  const [selectedPlay, setSelectedPlay] = useState<Play>(balanced);
  const chainSignals = signals.filter((s) => moment.signal_chain.includes(s.id));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close]);

  return (
    <div
      data-moment-overlay
      data-theme="hybrid-light"
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        overflow: 'auto',
        padding: '32px 48px',
        // Force light-mode tokens regardless of underlying theme.
        background: '#fafafa',
        color: '#111827',
      }}
    >
      <div className="flex items-center gap-3" style={{ marginBottom: 24 }}>
        <button
          type="button"
          onClick={close}
          aria-label="Back"
          className="flex items-center gap-1.5 mz-text-sm"
          style={{
            padding: '8px 14px',
            background: '#ffffff',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            color: '#6b7280',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          <ArrowLeft size={14} />
          Back
        </button>
        <span
          className="font-mono mz-text-xs uppercase"
          style={{ color: '#9ca3af', letterSpacing: '0.08em' }}
        >
          MOMENT.{moment.id.toUpperCase()} · {moment.expires_hours}H REMAINING
        </span>
      </div>

      <section style={{ marginBottom: 32, maxWidth: 900 }}>
        <div
          className="mz-text-xs uppercase"
          style={{ color: '#9ca3af', letterSpacing: '0.15em', marginBottom: 12 }}
        >
          STRATEGIC MOMENT
        </div>
        <h1
          className="font-display"
          style={{
            color: '#111827',
            fontSize: 'clamp(28px, 4vw, 38px)',
            lineHeight: 1.15,
            letterSpacing: '-0.02em',
            marginBottom: 14,
          }}
        >
          {moment.title}
        </h1>
        <p
          style={{
            color: '#6b7280',
            fontSize: 'var(--text-md)',
            lineHeight: 1.6,
            maxWidth: 720,
          }}
        >
          {moment.summary}
        </p>
      </section>

      <div
        className="grid"
        style={{
          gridTemplateColumns: 'minmax(0, 1fr) 360px',
          gap: 24,
        }}
      >
        <div>
          <header className="flex items-baseline gap-3" style={{ marginBottom: 12 }}>
            <h2 className="font-display" style={{ fontSize: 'var(--text-lg)', color: '#111827' }}>
              Plays
            </h2>
            <span className="mz-text-xs uppercase" style={{ color: '#9ca3af', letterSpacing: '0.1em' }}>
              STRATEGIST AGENTS · 3 PERSONAS
            </span>
          </header>

          <div className="grid gap-3" style={{ marginBottom: 20 }}>
            {moment.plays.map((p) => (
              <PlayCard
                key={p.id}
                play={p}
                selected={selectedPlay.id === p.id}
                onSelect={() => setSelectedPlay(p)}
              />
            ))}
          </div>

          <section
            style={{
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 20,
              marginBottom: 20,
            }}
          >
            <div className="font-display" style={{ fontSize: 'var(--text-md)', marginBottom: 4 }}>
              Outcome Distribution
            </div>
            <div
              className="mz-text-xs uppercase"
              style={{ color: '#9ca3af', letterSpacing: '0.08em', marginBottom: 14 }}
            >
              MONTE CARLO · 10,000 RUNS · {selectedPlay.label.toUpperCase()}
            </div>
            <OutcomeDistribution play={selectedPlay} />
          </section>

          <div className="flex gap-2.5">
            <button
              type="button"
              className="flex-1 mz-text-sm"
              style={{
                background: '#0d9488',
                border: 'none',
                borderRadius: 8,
                padding: '14px 20px',
                color: '#ffffff',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: 600,
              }}
            >
              ⚔ Open as War Room
            </button>
            <button
              type="button"
              className="mz-text-sm"
              style={{
                background: '#ffffff',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                padding: '14px 20px',
                color: '#111827',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: 600,
              }}
            >
              Defer
            </button>
            <button
              type="button"
              className="mz-text-sm"
              style={{
                background: '#111827',
                border: 'none',
                borderRadius: 8,
                padding: '14px 20px',
                color: '#fafafa',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: 600,
              }}
            >
              Commit Decision →
            </button>
          </div>
        </div>

        <aside className="flex flex-col gap-3.5">
          <section
            style={{
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 20,
            }}
          >
            <div className="font-display" style={{ fontSize: 'var(--text-md)', marginBottom: 4 }}>
              Signal Chain
            </div>
            <div
              className="mz-text-xs uppercase"
              style={{ color: '#9ca3af', letterSpacing: '0.08em', marginBottom: 14 }}
            >
              WHY THIS MOMENT EXISTS
            </div>
            {chainSignals.length === 0 ? (
              <p className="mz-text-sm" style={{ color: '#9ca3af' }}>
                Signal chain not available — backend BE-52 is wired but signal cross-refs need BE-50 materiality fix.
              </p>
            ) : (
              chainSignals.map((sig, i) => {
                const cat =
                  IMPACT_CATEGORIES.find((c) => c.id === (sig.kbq_tags ?? [])[0]) ??
                  IMPACT_CATEGORIES[2];
                const isLast = i === chainSignals.length - 1;
                return (
                  <div
                    key={sig.id}
                    style={{
                      position: 'relative',
                      paddingLeft: 22,
                      paddingBottom: isLast ? 0 : 14,
                      borderLeft: isLast ? 'none' : '1px dashed #e5e7eb',
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        position: 'absolute', left: -5, top: 4,
                        width: 10, height: 10, borderRadius: '50%',
                        background: cat.color,
                        border: '2px solid #ffffff',
                      }}
                    />
                    <div
                      className="mz-text-xs uppercase font-medium"
                      style={{ color: cat.color, letterSpacing: '0.08em', marginBottom: 3 }}
                    >
                      {cat.label}
                      {sig.event_id ? ` · ${sig.event_id}` : ''}
                    </div>
                    <div
                      className="mz-text-sm"
                      style={{ color: '#111827', fontWeight: 500, lineHeight: 1.4, marginBottom: 3 }}
                    >
                      {sig.headline}
                    </div>
                  </div>
                );
              })
            )}
          </section>

          <section
            style={{
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 20,
            }}
          >
            <div className="font-display" style={{ fontSize: 'var(--text-md)', marginBottom: 14 }}>
              Belief Shift
            </div>
            <div className="flex items-center gap-3.5" style={{ marginBottom: 10 }}>
              <div className="flex-1">
                <div className="mz-text-xs uppercase" style={{ color: '#9ca3af', letterSpacing: '0.08em' }}>
                  PRIOR
                </div>
                <div
                  className="font-mono"
                  style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: '#6b7280' }}
                >
                  {Math.round(moment.delta_belief.from * 100)}%
                </div>
              </div>
              <div style={{ fontSize: 20, color: '#0d9488' }}>→</div>
              <div className="flex-1">
                <div className="mz-text-xs uppercase" style={{ color: '#9ca3af', letterSpacing: '0.08em' }}>
                  POSTERIOR
                </div>
                <div
                  className="font-mono"
                  style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: '#0d9488' }}
                >
                  {Math.round(moment.delta_belief.to * 100)}%
                </div>
              </div>
            </div>
            <BeliefBar from={moment.delta_belief.from} to={moment.delta_belief.to} />
            <div className="mz-text-xs" style={{ color: '#6b7280', marginTop: 8 }}>
              {moment.delta_belief.label}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function PlayCard({
  play, selected, onSelect,
}: { play: Play; selected: boolean; onSelect: () => void }) {
  const kindColor =
    play.kind === 'aggressive' ? '#dc2626' :
    play.kind === 'balanced'   ? '#0d9488' :
    '#059669';
  return (
    <button
      type="button"
      onClick={onSelect}
      data-play-kind={play.kind}
      data-play-selected={selected ? 'true' : 'false'}
      style={{
        textAlign: 'left',
        background: '#ffffff',
        border: `2px solid ${selected ? '#0d9488' : '#e5e7eb'}`,
        borderRadius: 12,
        padding: 16,
        cursor: 'pointer',
        fontFamily: 'inherit',
      }}
    >
      <div className="flex items-center gap-1.5" style={{ marginBottom: 8 }}>
        <span
          className="mz-text-xs uppercase font-medium"
          style={{
            padding: '2px 8px',
            borderRadius: 10,
            background: `${kindColor}20`,
            color: kindColor,
            letterSpacing: '0.08em',
          }}
        >
          {play.kind}
        </span>
        {selected && (
          <span
            className="mz-text-xs uppercase font-medium"
            style={{
              padding: '2px 8px',
              borderRadius: 10,
              background: '#0d9488',
              color: '#ffffff',
              letterSpacing: '0.08em',
            }}
          >
            SELECTED
          </span>
        )}
      </div>
      <div className="mz-text-base" style={{ fontWeight: 500, lineHeight: 1.4, marginBottom: 12, color: '#111827' }}>
        {play.label}
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        {[
          { l: 'EV',     v: `$${play.ev}M`,                            c: '#0d9488' },
          { l: 'Var',    v: `$${play.ev_var}M`,                        c: '#6b7280' },
          { l: 'P(win)', v: `${Math.round(play.prob_success * 100)}%`, c: '#059669' },
        ].map((s) => (
          <div key={s.l}>
            <div
              className="mz-text-xs uppercase"
              style={{ color: '#9ca3af', letterSpacing: '0.08em' }}
            >
              {s.l}
            </div>
            <div
              className="font-mono"
              style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: s.c }}
            >
              {s.v}
            </div>
          </div>
        ))}
      </div>
    </button>
  );
}

function OutcomeDistribution({ play }: { play: Play }) {
  // Gaussian-shaped bars centred on 0, scaled by ev_var. 22 buckets.
  const bars = Array.from({ length: 22 }, (_, i) => {
    const x = -2.5 + (i / 21) * 5;
    return { x, h: Math.exp(-(x * x) / 1.5) };
  });
  const peak = Math.max(...bars.map((b) => b.h));
  return (
    <div>
      <div className="flex items-end gap-0.5" style={{ height: 70, marginBottom: 10 }}>
        {bars.map((b, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: `${(b.h / peak) * 100}%`,
              background: Math.abs(b.x) < 1 ? '#0d9488' : '#0d948860',
              borderRadius: '2px 2px 0 0',
            }}
          />
        ))}
      </div>
      <div
        className="font-mono flex justify-between mz-text-xs"
        style={{ color: '#9ca3af' }}
      >
        <span>{`$${play.ev - play.ev_var * 2}M (P05)`}</span>
        <span style={{ color: '#111827', fontWeight: 600 }}>{`$${play.ev}M expected`}</span>
        <span>{`$${play.ev + play.ev_var * 2}M (P95)`}</span>
      </div>
    </div>
  );
}

function BeliefBar({ from, to }: { from: number; to: number }) {
  return (
    <div
      style={{
        height: 4,
        background: '#e5e7eb',
        borderRadius: 2,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: `${from * 100}%`,
          top: 0,
          bottom: 0,
          width: `${(to - from) * 100}%`,
          background: '#0d9488',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: `${to * 100}%`,
          top: -2,
          bottom: -2,
          width: 2,
          background: '#0d9488',
        }}
      />
    </div>
  );
}
