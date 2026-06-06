/**
 * DI-5 — ForgePlaybooksView: light playbook authoring browse.
 *
 * Lists every Answer Playbook (DB-backed + YAML seed), opens one to read its
 * dimensions + full version history, and lets an uploader roll back a DB-backed
 * playbook to a prior version (itself a new forward version — the audit trail is
 * never rewritten). A full editor is a follow-up; this is the read + audit +
 * rollback surface that pairs with the live forge play loop.
 *
 * House style: design-token CSS variables + inline styles, no dynamic Tailwind
 * class names.
 */
import { useEffect, useState } from 'react';
import { BookOpen, History, RotateCcw, ChevronRight } from 'lucide-react';
import {
  playbooksApi,
  type PlaybookListItem,
  type PlaybookVersion,
} from '../../api';

export default function ForgePlaybooksView() {
  const [items, setItems] = useState<PlaybookListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = () => {
    setError(null);
    playbooksApi.list()
      .then(setItems)
      .catch((e: any) => setError(String(e?.message ?? e)));
  };

  useEffect(load, []);

  if (error) {
    return (
      <div data-testid="forge-playbooks-error" style={{
        color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13, padding: 'var(--space-4)',
      }}>{error}</div>
    );
  }

  if (items === null) {
    return (
      <div data-testid="forge-playbooks-loading" style={{
        fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)', padding: 'var(--space-5)',
      }}>Loading playbooks…</div>
    );
  }

  return (
    <div data-testid="forge-playbooks">
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
        textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 10,
      }}>
        Answer playbooks — encoded domain expertise ({items.length})
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((it) => (
          <PlaybookRow
            key={it.playbook.id}
            item={it}
            open={openId === it.playbook.id}
            onToggle={() => setOpenId(openId === it.playbook.id ? null : it.playbook.id)}
            onChanged={load}
          />
        ))}
        {items.length === 0 && (
          <div style={{ fontSize: 12.5, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
            No playbooks found.
          </div>
        )}
      </div>
    </div>
  );
}

function PlaybookRow({
  item, open, onToggle, onChanged,
}: {
  item: PlaybookListItem;
  open: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const { playbook, meta, source } = item;
  const dimCount = playbook.dimensions.length;

  return (
    <div
      data-testid={`forge-playbook-${playbook.id}`}
      style={{ border: '1px solid var(--color-line)', borderRadius: 12, overflow: 'hidden', background: 'var(--color-surface)' }}
    >
      <button
        data-testid={`forge-playbook-toggle-${playbook.id}`}
        onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '13px 15px',
          background: open ? 'var(--color-surface-2)' : 'transparent', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <BookOpen size={16} style={{ color: 'var(--color-ink-3)', flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>{playbook.id}</div>
          <div style={{ fontSize: 12, color: 'var(--color-ink-4)', marginTop: 2 }}>
            {dimCount} dimension{dimCount === 1 ? '' : 's'} · pack {playbook.pack}
          </div>
        </div>
        <SourceBadge source={source} version={meta.version} />
        <ChevronRight
          size={16}
          style={{ color: 'var(--color-ink-4)', flexShrink: 0, transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 160ms' }}
        />
      </button>

      {open && (
        <div style={{ padding: '4px 15px 15px', borderTop: '1px solid var(--color-line)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 12 }}>
            {playbook.dimensions.map((d) => (
              <div key={d.key} data-testid={`forge-playbook-dim-${d.key}`} style={{
                fontSize: 12.5, color: 'var(--color-ink-2)',
                display: 'flex', alignItems: 'baseline', gap: 8,
              }}>
                <span style={{ fontWeight: 600, color: 'var(--color-ink)' }}>{d.label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--color-ink-4)' }}>
                  {d.routes.join(', ') || 'no routes'}
                </span>
              </div>
            ))}
            {playbook.dimensions.length === 0 && (
              <span style={{ fontSize: 12, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>No dimensions.</span>
            )}
          </div>

          {source === 'db' ? (
            <VersionHistory playbookId={playbook.id} currentVersion={meta.version} onChanged={onChanged} />
          ) : (
            <div data-testid={`forge-playbook-seed-note-${playbook.id}`} style={{
              marginTop: 14, fontSize: 12, color: 'var(--color-ink-4)', fontStyle: 'italic',
            }}>
              Read-only YAML seed — play forge rounds to fork an editable, versioned copy.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SourceBadge({ source, version }: { source: 'db' | 'seed'; version: number | null }) {
  const isDb = source === 'db';
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.06em', textTransform: 'uppercase',
      padding: '2px 8px', borderRadius: 'var(--radius-pill)', flexShrink: 0,
      background: isDb ? 'var(--color-accent)' : 'var(--color-surface-3)',
      color: isDb ? 'var(--color-surface)' : 'var(--color-ink-4)',
    }}>
      {isDb ? `db · v${version ?? '?'}` : 'seed'}
    </span>
  );
}

function VersionHistory({
  playbookId, currentVersion, onChanged,
}: {
  playbookId: string;
  currentVersion: number | null;
  onChanged: () => void;
}) {
  const [versions, setVersions] = useState<PlaybookVersion[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    setErr(null);
    playbooksApi.versions(playbookId)
      .then(setVersions)
      .catch((e: any) => setErr(String(e?.message ?? e)));
  };

  useEffect(load, [playbookId]);

  const rollback = async (v: number) => {
    setBusy(v);
    try {
      await playbooksApi.rollback(playbookId, v, `rollback to v${v} from forge`);
      load();
      onChanged();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-testid={`forge-versions-${playbookId}`} style={{ marginTop: 16 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: 'var(--color-ink-4)', marginBottom: 8,
      }}>
        <History size={12} /> Version history
      </div>

      {err && <div style={{ color: 'var(--color-red)', fontSize: 12, marginBottom: 8 }}>{err}</div>}
      {versions === null && !err && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--color-ink-4)' }}>Loading history…</div>
      )}

      {versions && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {versions.map((v) => {
            const isCurrent = v.version === currentVersion;
            return (
              <div key={v.version} data-testid={`forge-version-${playbookId}-${v.version}`} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', borderRadius: 8,
                background: 'var(--color-surface-2)', fontSize: 12,
              }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--color-ink)',
                  minWidth: 30,
                }}>v{v.version}</span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em',
                  color: 'var(--color-ink-4)', minWidth: 56,
                }}>{v.action}</span>
                <span style={{ flex: 1, color: 'var(--color-ink-3)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {v.note || v.author || '—'}
                </span>
                {isCurrent ? (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em',
                    color: 'var(--color-green)',
                  }}>current</span>
                ) : (
                  <button
                    data-testid={`forge-rollback-${playbookId}-${v.version}`}
                    onClick={() => rollback(v.version)}
                    disabled={busy != null}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      fontFamily: 'var(--font-mono)', fontSize: 10, padding: '3px 9px',
                      borderRadius: 'var(--radius-pill)', border: '1px solid var(--color-line)',
                      background: 'var(--color-surface)', color: 'var(--color-ink-2)',
                      cursor: busy != null ? 'wait' : 'pointer', opacity: busy != null ? 0.6 : 1,
                    }}
                  >
                    <RotateCcw size={10} /> {busy === v.version ? 'restoring…' : 'restore'}
                  </button>
                )}
              </div>
            );
          })}
          {versions.length === 0 && (
            <span style={{ fontSize: 12, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>No version history.</span>
          )}
        </div>
      )}
    </div>
  );
}
