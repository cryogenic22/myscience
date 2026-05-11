import { useLocation } from 'react-router-dom';

/**
 * SPEC_041 §12a.2 — floating pill that opens the FeedbackWidget.
 *
 * Hidden on `/`, `/login`, and when `localStorage.mz_feedback_disabled
 * === 'true'`. Bottom-right by default; bottom-LEFT on `/workspace`
 * (Q4 sign-off — clears the chat send button).
 *
 * Click dispatches `mz:open-feedback` so FeedbackWidget can decouple
 * the trigger from the panel and listen globally.
 */

const HIDDEN_ROUTES = new Set(['/', '/login']);
const LEFT_ALIGNED_ROUTES = new Set(['/workspace']);

function isDisabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem('mz_feedback_disabled') === 'true';
}

export default function FeedbackButton() {
  const location = useLocation();
  const path = location.pathname;

  if (HIDDEN_ROUTES.has(path)) return null;
  if (isDisabled()) return null;

  const leftAligned = LEFT_ALIGNED_ROUTES.has(path);

  const positionStyle: React.CSSProperties = leftAligned
    ? { left: '24px', right: undefined }
    : { right: '24px', left: undefined };

  return (
    <button
      type="button"
      aria-label="Feedback"
      aria-haspopup="dialog"
      onClick={() => {
        window.dispatchEvent(new CustomEvent('mz:open-feedback'));
      }}
      style={{
        position: 'fixed',
        bottom: '24px',
        ...positionStyle,
        zIndex: 90,
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        padding: '10px 16px',
        background: 'var(--color-surface)',
        color: 'var(--color-ink)',
        border: '1px solid var(--color-line)',
        borderRadius: 'var(--radius-pill, 999px)',
        boxShadow: 'var(--shadow-sm)',
        fontFamily: 'var(--font-body)',
        fontSize: '13px',
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'box-shadow 140ms linear, transform 140ms cubic-bezier(0.16,1,0.3,1)',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-md)';
        (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-sm)';
        (e.currentTarget as HTMLElement).style.transform = 'none';
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '14px' }}>💬</span>
      <span>Feedback</span>
    </button>
  );
}
