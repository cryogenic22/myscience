import { useState, useRef, useEffect } from 'react';

/**
 * SPEC_030 — inline-edit primitive (Stripe-Dashboard-style).
 *
 * Renders the value as static text by default. Click → expands to <input>
 * pre-populated with the current value. Blur saves (calls onSave) and
 * collapses; escape reverts and collapses. No-op blur (unchanged value)
 * does NOT call onSave.
 *
 * locked=true prevents click-to-edit (used when brief.state forbids
 * mutation per SPEC_030 §8.3 affordance matrix).
 */

interface Props {
  /** The current value, rendered as static text and seeded into the editor. */
  value: string;
  /** What this field represents — used for aria-labels and the visible label. */
  label: string;
  /** Persist the new value. May throw / reject; we surface that to caller. */
  onSave: (next: string) => void | Promise<void>;
  /** When true, click-to-edit is disabled. Default false. */
  locked?: boolean;
  /** Optional placeholder when value is empty. */
  placeholder?: string;
  /** When true, render as multi-line <textarea>. Default false. */
  multiline?: boolean;
}

export default function BriefEditableField({
  value,
  label,
  onSave,
  locked = false,
  placeholder = '',
  multiline = false,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  const enter = () => {
    if (locked) return;
    setDraft(value);
    setEditing(true);
  };

  const exit = () => {
    setEditing(false);
  };

  const commit = async () => {
    if (draft === value) {
      // No-op blur: do not call onSave per spec test.
      exit();
      return;
    }
    try {
      setBusy(true);
      await onSave(draft);
      exit();
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setDraft(value);
      exit();
    } else if (!multiline && e.key === 'Enter') {
      e.preventDefault();
      void commit();
    }
  };

  if (!editing) {
    const display = value || placeholder;
    return (
      <span
        onClick={enter}
        role="text"
        aria-label={label}
        style={{
          cursor: locked ? 'default' : 'pointer',
          color: value ? 'var(--color-ink)' : 'var(--color-ink-4)',
          borderBottom: locked
            ? 'none'
            : '1px dotted transparent',
          transition: 'border-color 140ms linear',
          display: 'inline',
        }}
        onMouseEnter={(e) => {
          if (!locked) {
            (e.currentTarget as HTMLElement).style.borderBottomColor = 'var(--color-ink-4)';
          }
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.borderBottomColor = 'transparent';
        }}
      >
        {display}
      </span>
    );
  }

  const inputStyle = {
    width: '100%',
    background: 'var(--color-surface-2)',
    border: '1px solid var(--color-accent-soft, rgba(28,110,247,0.2))',
    borderRadius: 'var(--radius-input, 12px)',
    padding: '8px 12px',
    fontSize: '14px',
    color: 'var(--color-ink)',
    fontFamily: 'inherit',
    outline: 'none',
  };

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, position: 'relative', width: '100%' }}>
      {multiline ? (
        <textarea
          ref={inputRef as React.RefObject<HTMLTextAreaElement>}
          aria-label={label}
          role="textbox"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          rows={3}
          style={inputStyle}
        />
      ) : (
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          aria-label={label}
          type="text"
          role="textbox"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          style={inputStyle}
        />
      )}
      {busy && (
        <span
          aria-label="saving"
          role="status"
          aria-live="polite"
          style={{
            position: 'absolute',
            right: 8,
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: 11,
            color: 'var(--color-ink-3)',
          }}
        >
          ...saving
        </span>
      )}
    </span>
  );
}
