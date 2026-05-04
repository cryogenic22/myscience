import { useCallback, useEffect, useState } from 'react';
import { MessageSquare, Pencil, Trash2, Check, X } from 'lucide-react';
import { warRoomApi, type WarRoomComment } from '../../../api';

interface Props {
  roomId: string;
  ownerUserId: string | null;
  /** Optional: filter to a specific round's thread. */
  roundId?: string | null;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

function readUserId(): string | null {
  // Decode JWT payload (no verification — backend re-validates every request).
  // Used only as a UI hint for showing edit/delete buttons; if we get it wrong
  // the backend returns 403 and the user sees the error.
  if (typeof window === 'undefined') return null;
  try {
    const tok = window.localStorage.getItem('mz_auth_token');
    if (!tok) return null;
    const payload = tok.split('.')[1];
    if (!payload) return null;
    // Convert URL-safe base64 → standard, pad, decode
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded));
    return decoded?.sub ?? null;
  } catch {
    return null;
  }
}

export default function CommentsPanel({ roomId, ownerUserId, roundId = null }: Props) {
  const authed = hasToken();
  const currentUserId = readUserId();
  const [comments, setComments] = useState<WarRoomComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composer, setComposer] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await warRoomApi.listComments(roomId, roundId ?? undefined);
      setComments(r.comments);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [roomId, roundId]);

  useEffect(() => { void reload(); }, [reload]);

  const handlePost = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = composer.trim();
    if (!body || !authed) return;
    setBusy(true);
    setError(null);
    try {
      await warRoomApi.createComment(roomId, {
        body,
        round_id: roundId ?? undefined,
      });
      setComposer('');
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderRadius: '8px',
        padding: '14px 16px',
        background: 'var(--color-surface)',
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare size={14} style={{ color: 'var(--color-ink-3)' }} />
        <span
          className="text-[12px] font-medium"
          style={{ color: 'var(--color-ink)' }}
        >
          {roundId ? 'Round discussion' : 'Room discussion'} ({comments.length})
        </span>
      </div>

      {loading && comments.length === 0 ? (
        <div
          className="text-[11px]"
          style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
        >
          Loading comments…
        </div>
      ) : comments.length === 0 ? (
        <div
          className="text-[11px] mb-3"
          style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
        >
          No comments yet.{authed ? ' Be the first to add context.' : ' Log in to comment.'}
        </div>
      ) : (
        <div className="space-y-2 mb-3">
          {comments.map((c) => (
            <CommentItem
              key={c.id}
              comment={c}
              roomId={roomId}
              canEdit={!!currentUserId && currentUserId === c.author_user_id}
              canDelete={
                !!currentUserId &&
                (currentUserId === c.author_user_id || currentUserId === ownerUserId)
              }
              onChange={reload}
            />
          ))}
        </div>
      )}

      {error && (
        <div className="text-[11px] mb-2" style={{ color: '#B91C1C' }}>
          {error}
        </div>
      )}

      {authed ? (
        <form onSubmit={handlePost} className="flex flex-col gap-2">
          <textarea
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            placeholder="Add a comment…"
            rows={2}
            maxLength={4000}
            className="text-[12px] w-full"
            style={{
              padding: '8px 10px',
              borderRadius: '6px',
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink)',
              resize: 'vertical',
              minHeight: '52px',
            }}
          />
          <div className="flex items-center justify-between">
            <span
              className="text-[10px]"
              style={{ color: 'var(--color-ink-4)' }}
            >
              {composer.length} / 4000
            </span>
            <button
              type="submit"
              disabled={busy || !composer.trim()}
              className="text-[12px] font-medium"
              style={{
                padding: '5px 14px',
                borderRadius: '6px',
                background: busy || !composer.trim() ? 'var(--color-surface-2)' : 'var(--color-accent)',
                color: busy || !composer.trim() ? 'var(--color-ink-4)' : 'white',
                border: 'none',
                cursor: busy || !composer.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              {busy ? 'Posting…' : 'Post'}
            </button>
          </div>
        </form>
      ) : (
        <div className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          Log in (viewer or above) to add a comment.
        </div>
      )}
    </div>
  );
}

function CommentItem({
  comment,
  roomId,
  canEdit,
  canDelete,
  onChange,
}: {
  comment: WarRoomComment;
  roomId: string;
  canEdit: boolean;
  canDelete: boolean;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  const [busy, setBusy] = useState(false);

  const handleSave = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await warRoomApi.patchComment(roomId, comment.id, { body: draft.trim() });
      setEditing(false);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this comment?')) return;
    setBusy(true);
    try {
      await warRoomApi.deleteComment(roomId, comment.id);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        padding: '8px 12px',
        borderRadius: '6px',
        background: 'var(--color-surface-2)',
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span
          className="text-[11px] font-medium"
          style={{ color: 'var(--color-ink-2)' }}
        >
          {comment.author_display_name}
        </span>
        <span className="text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
          {comment.created_at ? new Date(comment.created_at).toLocaleString() : ''}
          {comment.edited_at && ' · edited'}
        </span>
        {(canEdit || canDelete) && !editing && (
          <div className="ml-auto flex items-center gap-1">
            {canEdit && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="opacity-60 hover:opacity-100"
                style={{ background: 'transparent', border: 'none', padding: '2px', color: 'var(--color-ink-3)' }}
                title="Edit"
                aria-label="Edit comment"
              >
                <Pencil size={11} />
              </button>
            )}
            {canDelete && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="opacity-60 hover:opacity-100"
                style={{ background: 'transparent', border: 'none', padding: '2px', color: 'var(--color-ink-3)' }}
                title="Delete"
                aria-label="Delete comment"
              >
                <Trash2 size={11} />
              </button>
            )}
          </div>
        )}
      </div>
      {editing ? (
        <div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            maxLength={4000}
            className="text-[12px] w-full"
            style={{
              padding: '6px 8px',
              borderRadius: '4px',
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink)',
              resize: 'vertical',
              minHeight: '44px',
            }}
          />
          <div className="flex items-center gap-1 mt-1">
            <button
              type="button"
              onClick={handleSave}
              disabled={busy || !draft.trim()}
              className="text-[10px] inline-flex items-center gap-1"
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                background: 'var(--color-accent)',
                color: 'white',
                border: 'none',
                cursor: busy || !draft.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              <Check size={10} /> Save
            </button>
            <button
              type="button"
              onClick={() => { setEditing(false); setDraft(comment.body); }}
              className="text-[10px] inline-flex items-center gap-1"
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                background: 'transparent',
                color: 'var(--color-ink-3)',
                border: '1px solid var(--color-line)',
              }}
            >
              <X size={10} /> Cancel
            </button>
          </div>
        </div>
      ) : (
        // React renders body as text → no XSS via {body}.
        <div
          className="text-[12px] whitespace-pre-wrap break-words"
          style={{ color: 'var(--color-ink)' }}
        >
          {comment.body}
        </div>
      )}
    </div>
  );
}
