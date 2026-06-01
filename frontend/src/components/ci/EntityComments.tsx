/**
 * UX02 — EntityComments.
 *
 * A reusable comment thread for any entity (target_type + target_id). Mount it
 * on a brief, scenario, insight, gap, dossier domain — anywhere collaboration
 * belongs. Loads the thread, renders comments (with @mention highlighting),
 * and posts new ones. Comment-based only (no real-time/CRDT).
 *
 * Header shows a count badge so it works as a compact, collapsible affordance.
 */
import { useCallback, useEffect, useState } from 'react';
import { commentsApi, type EntityComment } from '../../api';

interface Props {
  targetType: string;
  targetId: string;
  /** Optional heading; defaults to "Discussion". */
  title?: string;
}

const MENTION_RE = /(@[A-Za-z0-9_][\w.-]{0,63})/g;

function renderBody(body: string) {
  return body.split(MENTION_RE).map((part, i) =>
    MENTION_RE.test(part) ? (
      <span key={i} style={{ color: 'var(--color-accent)', fontWeight: 600 }}>{part}</span>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function EntityComments({ targetType, targetId, title = 'Discussion' }: Props) {
  const [comments, setComments] = useState<EntityComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    commentsApi.list(targetType, targetId)
      .then((r) => { if (!cancelled) setComments(r.comments); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [targetType, targetId]);

  useEffect(() => load(), [load]);

  const submit = async () => {
    const body = draft.trim();
    if (!body) return;
    setPosting(true);
    setError(null);
    try {
      const created = await commentsApi.add(targetType, targetId, body);
      setComments((prev) => [...prev, created]);
      setDraft('');
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setPosting(false);
    }
  };

  return (
    <section data-testid="entity-comments" aria-label="Comments" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
          {title}
        </span>
        <span
          data-testid="comments-count"
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, padding: '1px 7px',
            borderRadius: 'var(--radius-pill)', background: 'var(--color-surface-2)',
            color: 'var(--color-ink-3)', border: '1px solid var(--color-line)',
          }}
        >
          {comments.length}
        </span>
      </div>

      {error && (
        <p style={{ margin: 0, color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{error}</p>
      )}

      {loading ? (
        <div data-testid="comments-loading" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)' }}>
          Loading…
        </div>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {comments.length === 0 && (
            <li style={{ fontSize: 12.5, fontStyle: 'italic', color: 'var(--color-ink-3)' }}>
              No comments yet — start the discussion.
            </li>
          )}
          {comments.map((c) => (
            <li key={c.id} data-comment-id={c.id} style={{ padding: '8px 12px', background: 'var(--color-surface)', border: '1px solid var(--color-line)', borderLeft: '2px solid var(--color-line-2)' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 3 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-ink)' }}>{c.author_display_name}</span>
                {c.created_at && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-ink-4)' }}>
                    {c.created_at.slice(0, 16).replace('T', ' ')}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-ink-2)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {renderBody(c.body)}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <textarea
          data-testid="comment-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a comment… use @name to mention"
          rows={2}
          style={{
            flex: 1, resize: 'vertical', padding: '8px 10px', fontSize: 13,
            fontFamily: 'var(--font-body)', background: 'var(--color-bg)',
            border: '1px solid var(--color-line)', borderRadius: 6, color: 'var(--color-ink)',
          }}
        />
        <button
          type="button"
          data-testid="comment-submit"
          onClick={submit}
          disabled={posting || !draft.trim()}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.08em',
            textTransform: 'uppercase', padding: '8px 14px', fontWeight: 600,
            background: draft.trim() ? 'var(--color-accent)' : 'var(--color-surface-2)',
            color: draft.trim() ? 'var(--color-surface)' : 'var(--color-ink-3)',
            border: 'none', borderRadius: 'var(--radius-pill)',
            cursor: posting ? 'wait' : (draft.trim() ? 'pointer' : 'not-allowed'),
          }}
        >
          {posting ? 'Posting…' : 'Comment'}
        </button>
      </div>
    </section>
  );
}
