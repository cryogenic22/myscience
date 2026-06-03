/**
 * KBQ query surface — PB-SL10.
 *
 * "Ask a business question of an asset." Type an asset (semaglutide, Wegovy,
 * drug:tirzepatide) → the 8 Key Business Questions answered from the curated
 * signal/fact substrate, with parity. Each KBQ item is drillable to its
 * provenance (signal → fact → evidence), reusing the SL05 linked-facts shape.
 *
 * This is the read-first complement to the StandaloneDossier (8 ZS domains):
 * KBQs are the competitor-intelligence question framework; the dossier is the
 * evidence base. Both sit over the same fact ledger.
 */
import { useState } from 'react';
import { kbqApi, signalsApi, type EntityKbqs, type Signal } from '../../api';
import KbqDossier from './KbqDossier';
import FactClassGlyph from './FactClassGlyph';

const SUGGESTED = ['semaglutide', 'tirzepatide', 'Wegovy', 'Zepbound'];

function ProvenanceDrawer({ signal, loading, onClose }: {
  signal: Signal | null;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label="Signal provenance"
      style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(440px, 92vw)',
        background: 'var(--color-surface)', borderLeft: '1px solid var(--color-line)',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.12)', zIndex: 50,
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 18px', borderBottom: '1px solid var(--color-line)',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
          Provenance
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{ all: 'unset', cursor: 'pointer', color: 'var(--color-ink-3)', fontSize: 18, lineHeight: 1 }}
          aria-label="Close provenance"
        >
          ×
        </button>
      </div>

      <div style={{ padding: '18px', overflowY: 'auto' }}>
        {loading && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)' }}>
            Loading provenance…
          </div>
        )}
        {!loading && signal && (
          <>
            <h3 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 19, lineHeight: 1.3, color: 'var(--color-ink)' }}>
              {signal.headline}
            </h3>
            <div style={{ marginTop: 8, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <FactClassGlyph confidence_tier={signal.confidence_tier} size={14} withLabel />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-ink-3)' }}>
                {signal.impact_tier} impact
              </span>
            </div>
            {signal.summary && (
              <p style={{ marginTop: 12, fontSize: 13, lineHeight: 1.55, color: 'var(--color-ink-2)' }}>
                {signal.summary}
              </p>
            )}

            <div style={{ marginTop: 20 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 10 }}>
                Feeds {signal.linked_facts?.length ?? 0} fact{(signal.linked_facts?.length ?? 0) === 1 ? '' : 's'}
              </div>
              {(signal.linked_facts ?? []).length === 0 ? (
                <p style={{ fontSize: 12.5, fontStyle: 'italic', color: 'var(--color-ink-3)' }}>
                  No facts linked to this signal yet.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {(signal.linked_facts ?? []).map((f) => (
                    <div key={f.fact_id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      <FactClassGlyph factClass={(f.fact_class as any) ?? undefined} confidence_tier={null} size={14} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.45, color: 'var(--color-ink)' }}>
                          {f.claim || f.predicate}
                        </p>
                        <div style={{ marginTop: 3, display: 'flex', gap: 10, flexWrap: 'wrap', fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--color-ink-4)' }}>
                          <span>{f.predicate}</span>
                          {f.source_url ? (
                            <a href={f.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--color-accent)' }}>
                              {f.source_id || 'source'} →
                            </a>
                          ) : f.source_id ? (
                            <span>{f.source_id}</span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
        {!loading && !signal && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)' }}>
            Could not load this signal.
          </div>
        )}
      </div>
    </div>
  );
}

export default function KbqQueryTab() {
  const [asset, setAsset] = useState('');
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [data, setData] = useState<EntityKbqs | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [drawerSignal, setDrawerSignal] = useState<Signal | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const ask = async (a: string) => {
    const target = a.trim();
    if (!target) return;
    setSubmitted(target);
    setLoading(true);
    setError(null);
    try {
      setData(await kbqApi.byAsset(target));
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const openProvenance = async (signalId: string) => {
    setDrawerOpen(true);
    setDrawerLoading(true);
    setDrawerSignal(null);
    try {
      setDrawerSignal(await signalsApi.detail(signalId));
    } catch {
      setDrawerSignal(null);
    } finally {
      setDrawerLoading(false);
    }
  };

  return (
    <div data-testid="kbq-query" style={{ position: 'relative' }}>
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 8,
        }}>
          KBQ · ask the 8 key business questions of any asset
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            data-testid="kbq-asset-input"
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') ask(asset); }}
            placeholder="asset, e.g. semaglutide or drug:wegovy"
            style={{
              width: 320, padding: '8px 11px', fontSize: 13.5,
              fontFamily: 'var(--font-body)', background: 'var(--color-bg)',
              border: '1px solid var(--color-line)', borderRadius: 8, color: 'var(--color-ink)',
            }}
          />
          <button
            data-testid="kbq-ask"
            onClick={() => ask(asset)}
            disabled={loading || !asset.trim()}
            style={{
              padding: '9px 16px', fontSize: 13, fontWeight: 500,
              borderRadius: 'var(--radius-pill)', border: 'none',
              cursor: loading ? 'wait' : 'pointer',
              background: 'var(--color-ink)', color: 'var(--color-bg)',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Asking…' : 'Ask KBQs'}
          </button>
        </div>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11.5, color: 'var(--color-ink-4)' }}>Try:</span>
          {SUGGESTED.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => { setAsset(s); ask(s); }}
              style={{
                all: 'unset', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
                padding: '2px 8px', borderRadius: 'var(--radius-pill)',
                background: 'var(--color-surface-3)', color: 'var(--color-ink-2)',
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div data-testid="kbq-error" style={{ color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13, padding: 'var(--space-4)' }}>
          {error}
        </div>
      )}

      {loading && !data && (
        <div data-testid="kbq-loading" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)', padding: 'var(--space-5)' }}>
          Answering the 8 KBQs for {submitted}…
        </div>
      )}

      {!loading && !data && !error && (
        <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 15, color: 'var(--color-ink-3)', padding: 'var(--space-5)' }}>
          Type an asset above to see its Indications, Competitors, Clinical, Positioning,
          Sales &amp; Sentiment, SWOT, Pricing and Access — answered from the live evidence base.
        </div>
      )}

      {data && (
        <div data-testid="kbq-ready">
          <KbqDossier
            data={data}
            entityName={data.entity.name || submitted || `${data.entity.type}`}
            onOpenSignal={openProvenance}
            embedded
          />
        </div>
      )}

      {drawerOpen && (
        <>
          <div
            onClick={() => setDrawerOpen(false)}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.18)', zIndex: 49 }}
          />
          <ProvenanceDrawer
            signal={drawerSignal}
            loading={drawerLoading}
            onClose={() => setDrawerOpen(false)}
          />
        </>
      )}
    </div>
  );
}
