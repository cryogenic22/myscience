import { useEffect, useState } from 'react';
import { signalsApi, type Signal } from '../../api';
import {
  HELIX as H, catColor, catSoft, CAT_LABEL, IMPACT_TONE, IMPACT_WORD, fmtAge,
} from '../../lib/helix';

/**
 * Sensing Feed — reskinned to the Helix language (polish loop) and pointed at
 * entity-resolved /signals instead of the legacy /intelligence/feed.
 *
 * Fixes the three problems on the old feed: "SIGNAL: MARKET" everywhere (now
 * real entity names), "1% materiality" rings (now impact-tier encoding), and
 * the sparse boxed layout (now left-rail signal cards — no boxes around text).
 */

function primaryTag(s: Signal): string | undefined {
  return (s.kbq_tags && s.kbq_tags[0]) || undefined;
}

function SignalRow({ s, onFrame }: { s: Signal; onFrame: (s: Signal) => void }) {
  const tag = primaryTag(s);
  const color = catColor(tag);
  const tier = s.impact_tier ?? 'low';
  const entity = s.primary_entity_name && s.primary_entity_id !== 'market'
    ? s.primary_entity_name
    : 'Market';
  return (
    <div
      data-signal-row
      style={{
        display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 16,
        padding: '14px 18px',
        borderLeft: `2px solid ${tier === 'high' ? color : H.line}`,
        background: tier === 'high' ? catSoft(tag, 0.05) : 'transparent',
        borderRadius: '0 8px 8px 0',
      }}
    >
      {/* materiality rail — height encodes impact, color encodes category */}
      <div style={{ width: 4, alignSelf: 'stretch', minHeight: 44, background: H.line, borderRadius: 2, position: 'relative' }}>
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, borderRadius: 2,
          height: `${Math.round((s.impact_score ?? 0) * 100)}%`, background: color,
        }} />
      </div>

      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 5 }}>
          <span style={{
            fontFamily: H.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.08em',
            textTransform: 'uppercase', padding: '2px 7px', borderRadius: 4,
            background: catSoft(tag, 0.16), color,
          }}>
            {CAT_LABEL[tag ?? ''] ?? 'Signal'}
          </span>
          <span style={{
            fontFamily: H.mono, fontSize: 9.5, fontWeight: 600, letterSpacing: '0.08em',
            color: IMPACT_TONE[tier], textTransform: 'uppercase',
          }}>
            {IMPACT_WORD[tier]}
          </span>
          <span style={{ fontFamily: H.mono, fontSize: 9.5, color: H.faint, textTransform: 'uppercase' }}>
            {entity}
          </span>
          <span style={{ marginLeft: 'auto', fontFamily: H.mono, fontSize: 9.5, color: H.faint }}>
            {fmtAge(s.created_at)}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.45, color: H.ink, fontWeight: 500 }}>
          {s.headline}
        </p>
        {s.confidence_tier && (
          <span style={{ fontFamily: H.mono, fontSize: 9.5, color: H.dim, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {s.confidence_tier}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => onFrame(s)}
          style={{
            fontFamily: H.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.08em',
            textTransform: 'uppercase', padding: '7px 12px', borderRadius: 6,
            background: 'transparent', border: `1px solid ${H.line2}`, color: H.accent,
            cursor: 'pointer', whiteSpace: 'nowrap',
          }}
        >
          Frame →
        </button>
      </div>
    </div>
  );
}

export function SensingFeed({ onFrame }: { onFrame?: (s: Signal) => void } = {}) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    signalsApi.list({ limit: 40 })
      .then((r) => { if (!cancelled) setSignals(r.signals); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const handleFrame = onFrame ?? (() => {});

  return (
    <div data-helix-sensing style={{ background: H.bg, minHeight: '100%', padding: '28px 32px 80px' }}>
      <header style={{ marginBottom: 22 }}>
        <h2 style={{ margin: 0, fontFamily: H.serif, fontSize: 32, letterSpacing: '-0.02em', color: H.ink }}>
          Sensing Feed
        </h2>
        <p style={{ margin: '4px 0 0', fontFamily: H.mono, fontSize: 11, letterSpacing: '0.04em', color: H.dim }}>
          ALWAYS-ON SIGNAL MONITORING · {signals.length} SIGNALS
        </p>
      </header>

      {loading && <p style={{ color: H.dim, fontFamily: H.mono, fontSize: 12 }}>Sensing the market…</p>}
      {error && <p style={{ color: H.bad, fontFamily: H.mono, fontSize: 12 }}>Feed error: {error}</p>}
      {!loading && !error && signals.length === 0 && (
        <p style={{ color: H.dim, fontSize: 13 }}>No signals yet.</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {signals.map((s) => <SignalRow key={s.id} s={s} onFrame={handleFrame} />)}
      </div>
    </div>
  );
}
