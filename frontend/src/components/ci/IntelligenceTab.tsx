/**
 * IX-2 — IntelligenceTab.
 *
 * Consolidates the three former feed tabs — Sensing Feed (InboxTab), Daily
 * Digest (DigestTab), Signals DB (SignalsTab) — into ONE surface with a view
 * toggle. They were three fidelities of the same intelligence_feed + signals
 * backend; this makes them three views, not three destinations.
 *
 *   Digest      → assessed events, trust × recency (the triaged landing)
 *   Stream      → the raw sensing feed (live agent activity)
 *   Signals DB  → the structured, queryable SPEC-015 signal layer
 *
 * Old deep-links (?tab=inbox|digest|signals) map to the matching initial view
 * for back-compat; the nav now shows a single "Intelligence" entry.
 */
import { useState } from 'react';
import DigestTab from './DigestTab';
import InboxTab from './InboxTab';
import SignalsTab from './SignalsTab';

export type IntelView = 'digest' | 'stream' | 'signals';

interface Props {
  initialView?: IntelView;
  onOpenDecision: (id: string) => void;
  onOpenWarRoom: (id: string, signalKbq?: string) => void;
  onOpenInsights?: () => void;
  onAskInChat?: (q: string) => void;
}

const VIEWS: Array<{ key: IntelView; label: string }> = [
  { key: 'digest', label: 'Digest · triaged' },
  { key: 'stream', label: 'Stream · raw' },
  { key: 'signals', label: 'Signals DB · queryable' },
];

export default function IntelligenceTab({
  initialView = 'digest',
  onOpenDecision,
  onOpenWarRoom,
  onOpenInsights,
  onAskInChat,
}: Props) {
  const [view, setView] = useState<IntelView>(initialView);

  return (
    <div data-testid="intelligence-tab">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: 'var(--color-ink-3)',
        }}>
          Intelligence
        </span>
        <div
          role="tablist"
          aria-label="Intelligence view"
          style={{
            display: 'inline-flex', gap: 2, padding: 3,
            background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
            borderRadius: 'var(--radius-pill)',
          }}
        >
          {VIEWS.map((v) => {
            const on = v.key === view;
            return (
              <button
                key={v.key}
                role="tab"
                aria-selected={on}
                data-testid={`intel-view-${v.key}`}
                onClick={() => setView(v.key)}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.02em',
                  border: 'none', cursor: 'pointer', padding: '5px 13px',
                  borderRadius: 'var(--radius-pill)',
                  background: on ? 'var(--color-accent)' : 'transparent',
                  color: on ? 'var(--color-surface)' : 'var(--color-ink-3)',
                }}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      </div>

      {view === 'digest' && <DigestTab onAskInChat={onAskInChat} />}
      {view === 'stream' && (
        <InboxTab
          onOpenDecision={onOpenDecision}
          onOpenWarRoom={onOpenWarRoom}
          onOpenSignals={() => setView('signals')}
          onOpenInsights={onOpenInsights}
        />
      )}
      {view === 'signals' && <SignalsTab onOpenWarRoom={onOpenWarRoom} />}
    </div>
  );
}
