/**
 * KBQ Dossier (presentational) — PB-SL10.
 *
 * The 8 Key Business Questions answered for one entity, with parity. Rewritten
 * for the SL10 query surface to drop the locked-dark "war room" palette (the
 * "everything is black" complaint) in favour of the design-token theme, so it
 * honours light/dark and reads cleanly inside the cockpit. Each KBQ is a panel
 * separated by a 2px left accent-rail (its category colour) + a tone-shifted
 * surface, not a 1px outline. Every item carries a fact-class glyph and is
 * clickable to open its signal → fact → evidence provenance (reuses SL05).
 */
import type { EntityKbqs, KbqItem, KbqView } from '../../api';
import FactClassGlyph from './FactClassGlyph';

// Category accent hue per KBQ (OKLCH, fixed L/C, hue only). Mid-lightness so it
// works as an accent rail on either a light or dark surface.
const KBQ_HUE: Record<number, number> = {
  1: 45, 2: 270, 3: 170, 4: 25, 5: 220, 6: 270, 7: 145, 8: 145,
};
const hue = (k: number) => `oklch(0.62 0.16 ${KBQ_HUE[k] ?? 200})`;
const hueSoft = (k: number, a = 0.08) => `oklch(0.62 0.16 ${KBQ_HUE[k] ?? 200} / ${a})`;

const IMPACT_TONE: Record<string, string> = {
  high: 'var(--color-red, #dc2626)',
  medium: 'var(--color-amber, #d97706)',
  low: 'var(--color-ink-4)',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function ItemRow({
  item,
  last,
  onOpen,
}: {
  item: KbqItem;
  last: boolean;
  onOpen?: (signalId: string) => void;
}) {
  // Signal items open the provenance drawer (signal → fact → evidence). Fact
  // items are already the ledger leaf — they show their source link inline.
  const isFact = item.source === 'fact';
  const clickable = Boolean(onOpen && item.signal_id && !isFact);
  return (
    <div
      data-kbq-item
      data-kbq-source={item.source ?? 'signal'}
      onClick={clickable ? () => onOpen!(item.signal_id as string) : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '11px 0',
        width: '100%', boxSizing: 'border-box',
        borderBottom: last ? 'none' : '1px solid var(--color-line)',
        cursor: clickable ? 'pointer' : 'default',
      }}
      title={clickable ? 'View provenance — signal → fact → evidence' : undefined}
    >
      <span aria-hidden style={{
        width: 6, height: 6, borderRadius: 999, marginTop: 7, flexShrink: 0,
        background: IMPACT_TONE[item.impact_tier ?? 'low'] ?? 'var(--color-ink-4)',
      }} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink)' }}>
          {item.claim}
        </p>
        <div style={{ marginTop: 5, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', fontFamily: 'var(--font-mono)' }}>
          {/* Fact items glyph from their explicit class; signals derive it. */}
          <FactClassGlyph
            factClass={isFact ? ((item.fact_class as any) ?? undefined) : undefined}
            confidence_tier={item.confidence_tier}
            size={13}
          />
          {item.confidence_tier && (
            <span style={{ fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
              {item.confidence_tier}
            </span>
          )}
          {item.evidence_ids.length > 0 && (
            <span style={{ fontSize: 9.5, color: 'var(--color-ink-4)' }}>
              {item.evidence_ids.length} EVIDENCE
            </span>
          )}
          {isFact && item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{ fontSize: 9.5, color: 'var(--color-accent)' }}
            >
              {item.source_label || 'source'} ↗
            </a>
          )}
          {fmtDate(item.date) && (
            <span style={{ fontSize: 9.5, color: 'var(--color-ink-4)' }}>{fmtDate(item.date)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function KbqCard({ view, onOpenSignal }: { view: KbqView; onOpenSignal?: (id: string) => void }) {
  const c = hue(view.kbq);
  const empty = view.status === 'insufficient' || view.items.length === 0;
  return (
    <section
      data-kbq={view.kbq}
      data-kbq-status={view.status}
      className="ds-card"
      style={{
        background: empty
          ? 'var(--color-surface)'
          : `linear-gradient(${hueSoft(view.kbq, 0.06)}, ${hueSoft(view.kbq, 0.02)}), var(--color-surface)`,
        borderLeft: `2px solid ${empty ? 'var(--color-line)' : c}`,
        borderRadius: '0 10px 10px 0',
        boxShadow: 'none',
        padding: '16px 18px',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 21, letterSpacing: '-0.01em', color: 'var(--color-ink)' }}>
          {view.title}
        </h3>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', color: empty ? 'var(--color-ink-4)' : c }}>
          KBQ-{view.kbq}
        </span>
      </div>
      {empty ? (
        <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--color-ink-3)', fontStyle: 'italic', fontFamily: 'var(--font-display)' }}>
          Insufficient evidence — no signals yet for this question.
        </p>
      ) : (
        <div>
          {view.items.map((it, i) => (
            <ItemRow
              key={(it.signal_id || it.fact_id || 'item') + i}
              item={it}
              last={i === view.items.length - 1}
              onOpen={onOpenSignal}
            />
          ))}
        </div>
      )}
    </section>
  );
}

interface Props {
  data: EntityKbqs;
  entityName: string;
  /** Open the provenance drawer for a KBQ item's underlying signal (SL05). */
  onOpenSignal?: (signalId: string) => void;
  /** When true, render without the full-page header/shell (embedded in a tab). */
  embedded?: boolean;
}

export default function KbqDossier({ data, entityName, onOpenSignal, embedded }: Props) {
  const pct = Math.round((data.completeness ?? 0) * 100);

  const grid = (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
      gap: 14, alignItems: 'start',
    }}>
      {data.kbqs.map((v) => <KbqCard key={v.kbq} view={v} onOpenSignal={onOpenSignal} />)}
    </div>
  );

  const header = (
    <header style={{ marginBottom: 30 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
        {data.entity.type} dossier
      </div>
      <h1 style={{ margin: '8px 0 0', fontFamily: 'var(--font-display)', fontSize: 46, lineHeight: 1.05, letterSpacing: '-0.025em', color: 'var(--color-ink)' }}>
        {entityName}
      </h1>
      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, maxWidth: 300, height: 4, borderRadius: 2, background: 'var(--color-line)', overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: 'var(--color-accent)', transition: 'width 300ms cubic-bezier(0.16,1,0.3,1)' }} />
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-3)' }}>
          <span style={{ color: 'var(--color-ink)' }}>{pct}%</span> KBQ COVERAGE
        </span>
      </div>
    </header>
  );

  if (embedded) {
    return (
      <div data-helix-dossier>
        {header}
        {grid}
      </div>
    );
  }

  return (
    <div data-helix-dossier style={{ background: 'var(--color-bg)', color: 'var(--color-ink)', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '36px 28px 96px' }}>
        {header}
        {grid}
      </div>
    </div>
  );
}
