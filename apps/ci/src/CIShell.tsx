import { useState } from 'react';
import { Sidebar, type CISurface } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { DailyDigest } from './surfaces/DailyDigest';

const SURFACE_PLACEHOLDER: Record<Exclude<CISurface, 'digest'>, { title: string; body: string }> = {
  watchlist:  { title: 'Watchlist',         body: 'Phase 1 sprint C5. Personal · team · subscription.' },
  alerts:     { title: 'Alerts',            body: 'Phase 1 sprint C7. Rule editor + delivery history.' },
  reviewer:   { title: 'Reviewer Queue',    body: 'Phase 1 sprint C6. Side-by-side evidence + approve/edit/reject.' },
  briefs:     { title: 'Briefs',            body: 'Phase 1.5. Composer + reviewer queue + versioned artifacts.' },
  trackers:   { title: 'Trackers',          body: 'Phase 1.5. Trial · PDUFA · LOE · Deal · Exec · Earnings.' },
  health:     { title: 'Connector Health',  body: 'Phase 1.5. Per-source freshness · error rate · doc volume.' },
};

/**
 * CI module shell. Skeleton — surfaces are placeholder cards except DailyDigest.
 *
 * Real routing (TanStack Router) and per-surface implementations land in
 * Phase 1 swimlane C (sprints C2–C8).
 */
export function CIShell() {
  const [surface, setSurface] = useState<CISurface>('digest');

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '232px 1fr',
        minHeight: '100vh',
        background: 'var(--mz-color-canvas)',
      }}
    >
      <Sidebar active={surface} onChange={setSurface} />
      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <TopBar />
        <main
          style={{
            flex: 1,
            padding: 'var(--mz-space-6)',
            overflow: 'auto',
            maxWidth: 1180,
            margin: '0 auto',
            width: '100%',
          }}
        >
          {surface === 'digest' ? (
            <DailyDigest />
          ) : (
            <Placeholder
              title={SURFACE_PLACEHOLDER[surface].title}
              body={SURFACE_PLACEHOLDER[surface].body}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h1
        style={{
          fontFamily: 'var(--mz-font-display)',
          fontSize: 'var(--mz-text-display-2)',
          fontWeight: 'var(--mz-weight-semibold)',
          letterSpacing: 'var(--mz-tracking-tight)',
          margin: 0,
        }}
      >
        {title}
      </h1>
      <p style={{ color: 'var(--mz-color-text-secondary)', marginTop: 'var(--mz-space-2)' }}>
        {body}
      </p>
    </div>
  );
}
