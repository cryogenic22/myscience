/**
 * UX11 / L12 — engagement activity timeline.
 *
 * A dismissible drawer showing what happened on this engagement, newest first
 * (briefs, scenarios, insights, gap remediations, dossier assemblies) — human
 * and agent/system actions alike. Read-only view over the engagement's own
 * artifacts; an engagement with no activity shows an honest empty state.
 */
import { useEffect, useState } from 'react';
import { engagementActivityApi, type ActivityItem } from '../../api';

const KIND_TONE: Record<ActivityItem['kind'], string> = {
  brief: '#8B5CF6',
  scenario: '#0a5a3f',
  insight: '#1a4c80',
  gap: '#B45309',
  dossier: '#6B7AB8',
};

function relTime(iso: string | null): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const secs = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface Props {
  engagementId: string;
}

export default function ActivityDrawer({ engagementId }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setItems(null);
    setError(null);
    engagementActivityApi
      .list(engagementId)
      .then((r) => { if (!cancelled) setItems(r); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'failed to load'); });
    return () => { cancelled = true; };
  }, [open, engagementId]);

  return (
    <>
      <button
        data-testid="activity-drawer-trigger"
        aria-label="Open activity timeline"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.04em',
          textTransform: 'uppercase', padding: '7px 14px',
          borderRadius: 'var(--radius-pill)', cursor: 'pointer',
          border: '1px solid var(--color-line)', background: 'var(--color-surface)',
          color: 'var(--color-ink-2)',
        }}
      >
        Activity
      </button>

      {open && (
        <>
          <div
            data-testid="activity-drawer-backdrop"
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 45, background: 'rgba(0,0,0,0.18)' }}
          />
          <aside
            data-testid="activity-drawer-panel"
            role="dialog"
            aria-label="Engagement activity"
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 46,
              width: 'min(420px, 94vw)', padding: 'var(--space-5)',
              background: 'var(--color-surface)', borderLeft: '1px solid var(--color-line)',
              boxShadow: 'var(--shadow-lg)', overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--color-ink)' }}>
                  Activity
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-ink-4)' }}>
                  What happened on this engagement
                </div>
              </div>
              <button
                data-testid="activity-drawer-close"
                aria-label="Close activity"
                onClick={() => setOpen(false)}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 18, color: 'var(--color-ink-3)' }}
              >
                ×
              </button>
            </div>

            {error && <div data-testid="activity-error" style={{ color: 'var(--color-red)', fontSize: 13 }}>{error}</div>}
            {!error && items === null && (
              <div data-testid="activity-loading" style={{ color: 'var(--color-ink-4)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                Loading…
              </div>
            )}
            {!error && items !== null && items.length === 0 && (
              <div data-testid="activity-empty" style={{ color: 'var(--color-ink-3)', fontSize: 13, fontStyle: 'italic' }}>
                No activity yet — author a brief, assemble a dossier, or derive scenarios to start the timeline.
              </div>
            )}
            {!error && items !== null && items.length > 0 && (
              <ol data-testid="activity-list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {items.map((it, idx) => (
                  <li
                    key={`${it.kind}-${it.ref_id ?? idx}-${idx}`}
                    data-activity-kind={it.kind}
                    style={{ display: 'flex', gap: 10, padding: '9px 0', borderBottom: '1px solid var(--color-line)' }}
                  >
                    <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: 999, background: KIND_TONE[it.kind], marginTop: 6, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, color: 'var(--color-ink)', lineHeight: 1.4 }}>{it.summary}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--color-ink-4)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                        {it.actor_kind === 'system' ? 'automated' : 'by a teammate'} · {relTime(it.at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        </>
      )}
    </>
  );
}
