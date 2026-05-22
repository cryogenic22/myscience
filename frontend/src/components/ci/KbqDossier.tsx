/**
 * Polish loop — KBQ Dossier, in the Helix design language.
 *
 * Adopts the bespoke Helix system (Downloads/helix-core.jsx): a locked dark
 * "war room" palette, OKLCH category hues, Instrument Serif display +
 * JetBrains Mono metadata, and — crucially — NO boxes around text. Each KBQ
 * is a panel separated by a 2px left accent-rail (its category colour) +
 * a subtle background tint, not a 1px outline. This is the fix for the
 * "constrained borders around text" complaint.
 */
import { useEffect } from 'react';
import type { EntityKbqs, KbqItem, KbqView } from '../../api';

// ── Helix tokens (from helix-core.jsx) ──────────────────────────────
const H = {
  bg: '#0a0b0e', ink: '#e8eaed', ink2: '#c2c6cf', dim: '#8a8f99',
  faint: '#5a5f69', panel: '#12141a', panel2: '#181b22', line: '#23262d',
  accent: '#5eead4', ok: '#34d399', warn: '#fbbf24', bad: '#f87171',
  serif: "'Instrument Serif', 'Fraunces', Georgia, serif",
  mono: "'JetBrains Mono', 'DM Mono', ui-monospace, monospace",
};
// Category hue per KBQ (OKLCH, fixed L/C, hue only — Helix convention).
const KBQ_HUE: Record<number, number> = {
  1: 45, 2: 270, 3: 170, 4: 25, 5: 220, 6: 270, 7: 145, 8: 145,
};
const hue = (k: number) => `oklch(0.72 0.16 ${KBQ_HUE[k] ?? 200})`;
const hueSoft = (k: number, a = 0.1) => `oklch(0.72 0.16 ${KBQ_HUE[k] ?? 200} / ${a})`;

const IMPACT_TONE: Record<string, string> = { high: H.bad, medium: H.warn, low: H.faint };

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function ItemRow({ item, last }: { item: KbqItem; last: boolean }) {
  return (
    <div
      data-kbq-item
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '11px 0',
        borderBottom: last ? 'none' : `1px solid ${H.line}`,
      }}
    >
      <span aria-hidden style={{
        width: 6, height: 6, borderRadius: 999, marginTop: 7, flexShrink: 0,
        background: IMPACT_TONE[item.impact_tier ?? 'low'] ?? H.faint,
      }} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: H.ink }}>{item.claim}</p>
        <div style={{ marginTop: 5, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', fontFamily: H.mono }}>
          {item.confidence_tier && (
            <span style={{ fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: H.dim }}>
              {item.confidence_tier}
            </span>
          )}
          {item.evidence_ids.length > 0 && (
            <span style={{ fontSize: 9.5, color: H.faint }}>{item.evidence_ids.length} EVIDENCE</span>
          )}
          {fmtDate(item.date) && <span style={{ fontSize: 9.5, color: H.faint }}>{fmtDate(item.date)}</span>}
        </div>
      </div>
    </div>
  );
}

function KbqCard({ view }: { view: KbqView }) {
  const c = hue(view.kbq);
  const empty = view.status === 'insufficient' || view.items.length === 0;
  return (
    <section
      data-kbq={view.kbq}
      data-kbq-status={view.status}
      className="ds-card"
      style={{
        background: empty ? H.panel : `linear-gradient(${hueSoft(view.kbq, 0.05)}, ${hueSoft(view.kbq, 0.02)}), ${H.panel}`,
        borderLeft: `2px solid ${empty ? H.line : c}`,
        borderRadius: '0 10px 10px 0',
        boxShadow: 'none',
        padding: '16px 18px',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
        <h3 style={{ margin: 0, fontFamily: H.serif, fontSize: 21, letterSpacing: '-0.01em', color: H.ink }}>
          {view.title}
        </h3>
        <span style={{ fontFamily: H.mono, fontSize: 10, letterSpacing: '0.1em', color: empty ? H.faint : c }}>
          KBQ-{view.kbq}
        </span>
      </div>
      {empty ? (
        <p style={{ margin: '4px 0 0', fontSize: 12.5, color: H.dim, fontStyle: 'italic', fontFamily: H.serif }}>
          Insufficient evidence — no signals yet for this question.
        </p>
      ) : (
        <div>
          {view.items.map((it, i) => (
            <ItemRow key={it.signal_id + i} item={it} last={i === view.items.length - 1} />
          ))}
        </div>
      )}
    </section>
  );
}

interface Props {
  data: EntityKbqs;
  entityName: string;
}

export default function KbqDossier({ data, entityName }: Props) {
  const pct = Math.round((data.completeness ?? 0) * 100);

  // Inject the Helix display/mono fonts once (graceful fallback if blocked).
  useEffect(() => {
    const id = 'helix-fonts';
    if (typeof document === 'undefined' || document.getElementById(id)) return;
    const l = document.createElement('link');
    l.id = id; l.rel = 'stylesheet';
    l.href = 'https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;600&display=swap';
    document.head.appendChild(l);
  }, []);

  return (
    <div data-helix-dossier style={{ background: H.bg, color: H.ink, minHeight: '100vh' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '36px 28px 96px' }}>
        <header style={{ marginBottom: 30 }}>
          <div style={{ fontFamily: H.mono, fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: H.dim }}>
            {data.entity.type} dossier
          </div>
          <h1 style={{ margin: '8px 0 0', fontFamily: H.serif, fontSize: 46, lineHeight: 1.05, letterSpacing: '-0.025em', color: H.ink }}>
            {entityName}
          </h1>
          <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1, maxWidth: 300, height: 4, borderRadius: 2, background: H.line, overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: H.accent, transition: 'width 300ms cubic-bezier(0.16,1,0.3,1)' }} />
            </div>
            <span style={{ fontFamily: H.mono, fontSize: 11, color: H.dim }}>
              <span style={{ color: H.ink }}>{pct}%</span> KBQ COVERAGE
            </span>
          </div>
        </header>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: 14, alignItems: 'start',
        }}>
          {data.kbqs.map((v) => <KbqCard key={v.kbq} view={v} />)}
        </div>
      </div>
    </div>
  );
}
