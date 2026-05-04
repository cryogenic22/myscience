import { useEffect, useRef, useState } from 'react';
import {
  MoreHorizontal, Pencil, Archive, ArchiveRestore, Link as LinkIcon,
  XCircle, RefreshCw,
} from 'lucide-react';
import { warRoomApi, type WarRoom } from '../../../api';

interface Props {
  room: WarRoom;
  onChange: (updated: WarRoom) => void;
  onClosed?: () => void;
}

function isOwner(room: WarRoom): boolean {
  // Decode JWT payload to compare to owner_user_id (UI hint only — backend
  // enforces). See CommentsPanel.readUserId for the same pattern.
  if (typeof window === 'undefined') return false;
  try {
    const tok = window.localStorage.getItem('mz_auth_token');
    if (!tok) return false;
    const payload = tok.split('.')[1];
    if (!payload) return false;
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded));
    return decoded?.sub === room.owner_user_id;
  } catch {
    return false;
  }
}

export default function RoomActionsMenu({ room, onChange, onClosed }: Props) {
  const owner = isOwner(room);
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(room.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareToast, setShareToast] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleRename = async () => {
    const title = draftTitle.trim();
    if (!title || title === room.title) {
      setRenaming(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await warRoomApi.patch(room.id, { title });
      onChange(updated);
      setRenaming(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleArchive = async (archived: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await warRoomApi.patch(room.id, { archived });
      onChange(updated);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleStatus = async (status: 'active' | 'closed') => {
    setBusy(true);
    setError(null);
    try {
      const updated = await warRoomApi.patch(room.id, { status });
      onChange(updated);
      setOpen(false);
      if (status === 'closed' && onClosed) onClosed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleShare = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setShareToast('Share URL copied');
      setTimeout(() => setShareToast(null), 2200);
    } catch {
      setShareToast('Could not copy — URL is in the address bar');
      setTimeout(() => setShareToast(null), 2800);
    }
    setOpen(false);
  };

  return (
    <div ref={menuRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-[12px]"
        style={{
          padding: '6px 10px',
          borderRadius: '6px',
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
          color: 'var(--color-ink-2)',
          cursor: 'pointer',
        }}
        aria-label="Room actions"
      >
        <MoreHorizontal size={14} />
        Actions
      </button>

      {shareToast && (
        <div
          className="absolute right-0 mt-1 text-[11px]"
          style={{
            top: '100%',
            zIndex: 50,
            padding: '4px 10px',
            borderRadius: '4px',
            background: 'var(--color-ink)',
            color: 'var(--color-surface)',
            whiteSpace: 'nowrap',
          }}
        >
          {shareToast}
        </div>
      )}

      {open && (
        <div
          className="absolute right-0 mt-1"
          style={{
            top: '100%',
            zIndex: 40,
            minWidth: '220px',
            borderRadius: '6px',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            padding: '4px',
          }}
        >
          {renaming ? (
            <div style={{ padding: '8px 10px' }}>
              <input
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                placeholder="New title…"
                maxLength={300}
                autoFocus
                className="text-[12px] w-full"
                style={{
                  padding: '6px 8px',
                  borderRadius: '4px',
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink)',
                }}
              />
              <div className="flex gap-1 mt-2">
                <button
                  type="button"
                  onClick={handleRename}
                  disabled={busy || !draftTitle.trim()}
                  className="text-[11px]"
                  style={{
                    flex: 1, padding: '4px 8px', borderRadius: '4px',
                    background: 'var(--color-accent)',
                    color: 'white', border: 'none',
                    cursor: busy || !draftTitle.trim() ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  onClick={() => { setRenaming(false); setDraftTitle(room.title); }}
                  className="text-[11px]"
                  style={{
                    flex: 1, padding: '4px 8px', borderRadius: '4px',
                    background: 'transparent', color: 'var(--color-ink-3)',
                    border: '1px solid var(--color-line)',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <MenuItem
                icon={<LinkIcon size={13} />}
                label="Copy share URL"
                onClick={handleShare}
              />
              {owner && (
                <>
                  <MenuItem
                    icon={<Pencil size={13} />}
                    label="Rename"
                    onClick={() => setRenaming(true)}
                  />
                  {room.archived_at ? (
                    <MenuItem
                      icon={<ArchiveRestore size={13} />}
                      label="Unarchive"
                      onClick={() => handleArchive(false)}
                      disabled={busy}
                    />
                  ) : (
                    <MenuItem
                      icon={<Archive size={13} />}
                      label="Archive"
                      onClick={() => handleArchive(true)}
                      disabled={busy}
                    />
                  )}
                  {room.status === 'active' ? (
                    <MenuItem
                      icon={<XCircle size={13} />}
                      label="Close room"
                      onClick={() => handleStatus('closed')}
                      disabled={busy}
                      danger
                    />
                  ) : (
                    <MenuItem
                      icon={<RefreshCw size={13} />}
                      label="Re-open"
                      onClick={() => handleStatus('active')}
                      disabled={busy}
                    />
                  )}
                </>
              )}
              {!owner && (
                <div
                  className="text-[10px] px-3 py-2"
                  style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
                >
                  Owner-only actions hidden.
                </div>
              )}
              {error && (
                <div
                  className="text-[10px] px-3 py-2"
                  style={{ color: '#B91C1C' }}
                >
                  {error}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon, label, onClick, disabled, danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full text-left text-[12px] inline-flex items-center gap-2"
      style={{
        padding: '7px 10px',
        borderRadius: '4px',
        background: 'transparent',
        color: danger ? '#B91C1C' : 'var(--color-ink-2)',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
