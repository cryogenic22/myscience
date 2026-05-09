import { useEffect, useId, useRef, useState } from 'react';
import {
  feedbackApi,
  type FeedbackCategory,
  type FeedbackPriority,
  type FeedbackAttachment,
} from '../../api';
import { collectDiagnostics, clearDiagnostics } from '../../lib/diagnostics';

/**
 * SPEC_041 §12a.3 — chat-style feedback submission widget.
 *
 * Listens for `window 'mz:open-feedback'` to open. State machine:
 *   greeting → category_selected → description_provided
 *            → priority_selected → confirmed → submitted | error
 *
 * Each transition appends a message to the in-panel transcript so
 * users see what they've answered. Diagnostics + entity-context auto-
 * attach at submit time.
 */

type ChatState =
  | 'greeting'
  | 'category_selected'
  | 'description_provided'
  | 'priority_selected'
  | 'confirmed'
  | 'submitted'
  | 'error';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const CATEGORY_LABELS: Record<FeedbackCategory, string> = {
  bug: 'Bug',
  issue: 'Issue',
  enhancement: 'Enhancement',
  feature: 'Feature',
  data_quality: 'Data quality',
  data_request: 'Data request',
};

const CATEGORY_GLYPHS: Record<FeedbackCategory, string> = {
  bug: '🐞',
  issue: '⚠️',
  enhancement: '✨',
  feature: '🚀',
  data_quality: '📊',
  data_request: '🔍',
};

const CATEGORY_PROMPTS: Record<FeedbackCategory, string> = {
  bug: 'Describe the bug. What happened, what did you expect, and how can we reproduce it? You can paste a screenshot (Ctrl+V).',
  issue: 'Describe the issue you\'re hitting and how it impacts your workflow.',
  enhancement: 'Which feature would you like improved? How would the improvement help?',
  feature: 'Describe the new capability you\'d like and the use case it would solve.',
  data_quality: 'Which entity / KPI / number is wrong? Pasting a screenshot helps a lot.',
  data_request: 'What data are you missing? Which entity, which source, what depth?',
};

const PRIORITY_GLYPHS: Record<FeedbackPriority, string> = {
  low: '◯',
  medium: '◐',
  high: '◑',
  critical: '●',
};

const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_SIZE = 2 * 1024 * 1024;

function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function FeedbackWidget() {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ChatState>('greeting');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState('');
  const [priority, setPriority] = useState<FeedbackPriority>('medium');
  const [attachments, setAttachments] = useState<FeedbackAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);

  // Open on `mz:open-feedback` from FeedbackButton (or anywhere else).
  useEffect(() => {
    const handler = () => {
      setOpen(true);
      setState('greeting');
      setMessages([{ role: 'assistant', content: 'What kind of feedback do you have?' }]);
      setCategory(null);
      setDescription('');
      setDraft('');
      setPriority('medium');
      setAttachments([]);
      setError(null);
      setResultId(null);
    };
    window.addEventListener('mz:open-feedback', handler);
    return () => window.removeEventListener('mz:open-feedback', handler);
  }, []);

  // Esc closes; focus the close button on open.
  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Auto-scroll messages on append. JSDOM does not implement
  // scrollIntoView; the optional-chain guard keeps tests green.
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  if (!open) return null;

  const appendMessage = (role: 'user' | 'assistant', content: string) =>
    setMessages((prev) => [...prev, { role, content }]);

  const handleCategory = (cat: FeedbackCategory) => {
    setCategory(cat);
    appendMessage('user', `${CATEGORY_GLYPHS[cat]} ${CATEGORY_LABELS[cat]}`);
    appendMessage('assistant', CATEGORY_PROMPTS[cat]);
    setState('category_selected');
  };

  const handleSendDescription = () => {
    if (!draft.trim()) return;
    setDescription(draft.trim());
    appendMessage('user', draft.trim());
    appendMessage('assistant', 'How urgent is this?');
    setState('description_provided');
    setDraft('');
  };

  const handlePriority = (p: FeedbackPriority) => {
    setPriority(p);
    appendMessage('user', `${PRIORITY_GLYPHS[p]} ${p}`);
    appendMessage(
      'assistant',
      `Ready to submit a ${CATEGORY_LABELS[category!]} at ${p} priority. Looks right?`,
    );
    setState('priority_selected');
  };

  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) await addAttachment(file);
        return;
      }
    }
  };

  const addAttachment = async (file: File) => {
    if (attachments.length >= MAX_ATTACHMENTS) {
      appendMessage('assistant', `Maximum ${MAX_ATTACHMENTS} attachments.`);
      return;
    }
    if (file.size > MAX_ATTACHMENT_SIZE) {
      appendMessage('assistant', 'Attachment too large (max 2 MB).');
      return;
    }
    if (!file.type.startsWith('image/')) {
      appendMessage('assistant', 'Only images are accepted as screenshots.');
      return;
    }
    try {
      const dataUri = await fileToDataUri(file);
      const attachment: FeedbackAttachment = {
        data: dataUri,
        filename: file.name || `pasted-${Date.now()}.png`,
        mime_type: file.type,
        size_bytes: file.size,
      };
      setAttachments((prev) => [...prev, attachment]);
      appendMessage('user', `📎 ${attachment.filename}`);
    } catch {
      appendMessage('assistant', 'Could not read the image.');
    }
  };

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    if (!category) return;
    setBusy(true);
    setError(null);
    setState('confirmed');
    appendMessage('user', 'Submit it!');
    try {
      const firstSentence = description.split(/[.!?\n]/)[0]?.trim() || description;
      const title = firstSentence.length > 120 ? firstSentence.slice(0, 117) + '…' : firstSentence;

      const r = await feedbackApi.submit({
        category,
        title,
        description,
        priority,
        page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
        diagnostic_context: collectDiagnostics(),
        attachments,
      });

      const id = r.feedback.id;
      setResultId(id);
      appendMessage(
        'assistant',
        `Recorded! ID: ${id.slice(0, 12)}…\nWe'll triage on the next 45-min cron tick.`,
      );
      setState('submitted');
      clearDiagnostics();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      appendMessage('assistant', `Submission failed: ${msg}`);
      setState('error');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setOpen(false);
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 100,
        width: 'min(420px, 92vw)',
        maxHeight: 'min(640px, 80vh)',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: 'var(--radius-card, 16px)',
        boxShadow: 'var(--shadow-lg)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <header
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--color-line)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <h3
          id={titleId}
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--color-ink)',
          }}
        >
          Feedback
        </h3>
        <button
          ref={closeBtnRef}
          type="button"
          aria-label="close"
          onClick={() => setOpen(false)}
          className="btn btn-ghost btn-sm"
          style={{ padding: '4px 10px' }}
        >
          ×
        </button>
      </header>

      {/* Transcript */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '14px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              fontSize: '13px',
              fontFamily: 'var(--font-body)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-card, 12px)',
              background:
                m.role === 'user'
                  ? 'var(--color-accent-soft, rgba(28,110,247,0.08))'
                  : 'var(--color-surface-2)',
              color: m.role === 'user' ? 'var(--color-ink)' : 'var(--color-ink-2)',
              whiteSpace: 'pre-wrap',
            }}
          >
            {m.content}
          </div>
        ))}
        {busy && (
          <div
            style={{
              alignSelf: 'flex-start',
              fontSize: '12px',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
            }}
          >
            Submitting…
          </div>
        )}
        {error && state === 'error' && (
          <div
            role="alert"
            style={{
              alignSelf: 'stretch',
              fontSize: '12px',
              color: 'var(--color-red, #C0392B)',
              background: 'var(--color-red-soft, #FEF2F2)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-card, 12px)',
            }}
          >
            {error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Attachments strip */}
      {attachments.length > 0 && state !== 'submitted' && state !== 'error' && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            padding: '8px 18px',
            borderTop: '1px solid var(--color-line)',
            overflowX: 'auto',
          }}
        >
          {attachments.map((a, i) => (
            <div
              key={i}
              style={{ position: 'relative', flexShrink: 0 }}
            >
              <img
                src={a.data}
                alt={a.filename}
                style={{
                  width: 56,
                  height: 56,
                  objectFit: 'cover',
                  borderRadius: 'var(--radius-card, 8px)',
                  border: '1px solid var(--color-line)',
                }}
              />
              <button
                type="button"
                aria-label={`remove ${a.filename}`}
                onClick={() => removeAttachment(i)}
                style={{
                  position: 'absolute',
                  top: -6,
                  right: -6,
                  width: 18,
                  height: 18,
                  borderRadius: '50%',
                  background: 'var(--color-red, #C0392B)',
                  color: '#fff',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '11px',
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Action area — per state */}
      <footer
        style={{
          padding: '12px 18px',
          borderTop: '1px solid var(--color-line)',
        }}
      >
        {state === 'greeting' && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 8,
            }}
          >
            {(Object.keys(CATEGORY_LABELS) as FeedbackCategory[]).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => handleCategory(cat)}
                className="btn btn-secondary btn-sm"
                style={{ justifyContent: 'flex-start', gap: 6 }}
              >
                <span aria-hidden="true">{CATEGORY_GLYPHS[cat]}</span>
                <span>{CATEGORY_LABELS[cat]}</span>
              </button>
            ))}
          </div>
        )}

        {state === 'category_selected' && (
          <div style={{ display: 'flex', gap: 8 }}>
            <textarea
              aria-label="describe your feedback"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onPaste={(e) => void handlePaste(e)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault();
                  handleSendDescription();
                }
              }}
              placeholder="Describe… (Ctrl+V to paste a screenshot)"
              style={{
                flex: 1,
                background: 'var(--color-surface-2)',
                border: '1px solid var(--color-line)',
                borderRadius: 'var(--radius-input, 12px)',
                padding: '8px 12px',
                fontSize: '13px',
                fontFamily: 'inherit',
                color: 'var(--color-ink)',
                resize: 'vertical',
                outline: 'none',
              }}
              autoFocus
            />
            <button
              type="button"
              onClick={handleSendDescription}
              disabled={!draft.trim()}
              className="btn btn-accent btn-sm"
              aria-label="send"
            >
              Send
            </button>
          </div>
        )}

        {state === 'description_provided' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
            {(Object.keys(PRIORITY_GLYPHS) as FeedbackPriority[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => handlePriority(p)}
                className="btn btn-secondary btn-sm"
                style={{ flexDirection: 'column', gap: 2 }}
              >
                <span aria-hidden="true">{PRIORITY_GLYPHS[p]}</span>
                <span>{p}</span>
              </button>
            ))}
          </div>
        )}

        {state === 'priority_selected' && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              className="btn btn-accent btn-sm"
              style={{ flex: 1 }}
            >
              Submit feedback
            </button>
            <button type="button" onClick={reset} className="btn btn-secondary btn-sm">
              Start over
            </button>
          </div>
        )}

        {(state === 'submitted' || state === 'error') && (
          <button
            type="button"
            onClick={reset}
            className="btn btn-secondary btn-sm"
            style={{ width: '100%' }}
          >
            {resultId ? 'Close' : 'Try again'}
          </button>
        )}
      </footer>
    </div>
  );
}
