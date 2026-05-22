import type { Signal } from '../../api';
import {
  HELIX as H, catColor, catSoft, CAT_LABEL, IMPACT_TONE, IMPACT_WORD, fmtAge,
} from '../../lib/helix';

interface Props {
  signal: Signal;
  selected: boolean;
  onSelect: () => void;
}

/**
 * Signal list row — Helix language (polish loop). Category-coloured left rail
 * (no box), category chip + impact-tier word, mono metadata. Consistent with
 * the Sensing Feed. Selection lifts the background; no 1px outline.
 */
export default function SignalCard({ signal, selected, onSelect }: Props) {
  const tag = signal.kbq_tags?.[0];
  const color = catColor(tag);
  const tier = signal.impact_tier ?? 'low';
  const entity = signal.primary_entity_name && signal.primary_entity_id !== 'market'
    ? signal.primary_entity_name
    : 'Market';
  const railColor = selected ? H.accent : tier === 'high' ? color : H.line;

  return (
    <button
      type="button"
      onClick={onSelect}
      data-signal-card
      data-selected={selected}
      className="w-full text-left transition-colors"
      style={{
        padding: '12px 14px',
        background: selected ? H.panel2 : 'transparent',
        borderLeft: `2px solid ${railColor}`,
        borderBottom: `1px solid ${H.line}`,
      }}
    >
      {signal.superseded_by && (
        <div style={{ fontFamily: H.mono, fontSize: 9, color: H.warn, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>
          ⤴ Updates earlier signal
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 5 }}>
        <span style={{
          fontFamily: H.mono, fontSize: 9, fontWeight: 600, letterSpacing: '0.07em',
          textTransform: 'uppercase', padding: '1px 6px', borderRadius: 4,
          background: catSoft(tag, 0.16), color,
        }}>
          {CAT_LABEL[tag ?? ''] ?? 'Signal'}
        </span>
        <span style={{ fontFamily: H.mono, fontSize: 9, fontWeight: 600, letterSpacing: '0.07em', color: IMPACT_TONE[tier], textTransform: 'uppercase' }}>
          {IMPACT_WORD[tier]}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: H.mono, fontSize: 9, color: H.faint }}>
          {fmtAge(signal.created_at)}
        </span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.4, color: H.ink }}>
        {signal.headline}
      </div>
      <div style={{ fontFamily: H.mono, fontSize: 9.5, marginTop: 5, color: H.faint, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {entity}
        {signal.confidence_tier && <span> · {signal.confidence_tier}</span>}
      </div>
    </button>
  );
}
