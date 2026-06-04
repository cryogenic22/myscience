/**
 * UX12/UX13 — engagement export menu.
 *
 * Three deliverables (Executive Brief · Intelligence Dossier · Strategy Deck),
 * each a printable HTML document opened in a new tab (browser → PDF). The
 * endpoints are Bearer-auth'd, so we fetch-with-auth → blob → open rather than
 * a plain link. Agent-assembled, human-reviewed, then printed/shared.
 */
import { useState } from 'react';
import { engagementExportApi, type EngagementExportKind } from '../../api';

const ITEMS: { kind: EngagementExportKind; label: string }[] = [
  { kind: 'brief', label: 'Executive Brief' },
  { kind: 'dossier', label: 'Intelligence Dossier' },
  { kind: 'deck', label: 'Strategy Deck' },
];

export default function ExportMenu({ engagementId }: { engagementId: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<EngagementExportKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (kind: EngagementExportKind) => {
    setBusy(kind);
    setError(null);
    try {
      await engagementExportApi.open(engagementId, kind);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        data-testid="export-menu-trigger"
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] uppercase font-medium"
        style={{
          padding: '6px 12px', borderRadius: 6, border: '1px solid var(--color-line)',
          background: 'transparent', color: 'var(--color-ink-3)',
          letterSpacing: '0.06em', cursor: 'pointer',
        }}
      >
        Export ▾
      </button>
      {open && (
        <div
          data-testid="export-menu"
          style={{
            position: 'absolute', right: 0, top: 'calc(100% + 4px)', zIndex: 20,
            background: 'var(--color-surface)', border: '1px solid var(--color-line)',
            borderRadius: 8, boxShadow: 'var(--shadow-sm)', minWidth: 200, padding: 4,
          }}
        >
          {ITEMS.map((it) => (
            <button
              key={it.kind}
              type="button"
              data-export-kind={it.kind}
              onClick={() => void run(it.kind)}
              disabled={busy !== null}
              className="text-[12px]"
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '8px 12px', borderRadius: 6, border: 'none',
                background: 'transparent', color: 'var(--color-ink)',
                cursor: busy ? 'default' : 'pointer',
              }}
            >
              {busy === it.kind ? 'Opening…' : it.label}
            </button>
          ))}
          {error && (
            <div className="text-[11px]" style={{ padding: '4px 12px', color: '#B91C1C' }}>{error}</div>
          )}
        </div>
      )}
    </div>
  );
}
