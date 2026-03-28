import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ToastProps {
  message: string;
  variant: 'info' | 'success' | 'warning' | 'error';
  onDismiss: () => void;
  action?: { label: string; onClick: () => void };
  duration?: number;
}

const VARIANT_STYLES: Record<ToastProps['variant'], { bg: string; color: string; border: string }> = {
  info:    { bg: 'var(--color-accent-soft)', color: 'var(--color-accent)',  border: 'var(--color-accent)' },
  success: { bg: 'var(--color-green-soft)',  color: 'var(--color-green)',   border: 'var(--color-green)' },
  warning: { bg: 'var(--color-amber-soft)',  color: 'var(--color-amber)',   border: 'var(--color-amber)' },
  error:   { bg: 'var(--color-red-soft)',    color: 'var(--color-red)',     border: 'var(--color-red)' },
};

export function Toast({ message, variant, onDismiss, action, duration = 5000 }: ToastProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const style = VARIANT_STYLES[variant];

  useEffect(() => {
    timerRef.current = setTimeout(onDismiss, duration);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [onDismiss, duration]);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '12px 16px',
        borderRadius: '12px',
        background: style.bg,
        borderLeft: `3px solid ${style.border}`,
        boxShadow: 'var(--shadow-md)',
        fontFamily: 'var(--font-body)',
        animation: 'toast-slide-in 0.25s cubic-bezier(0.16,1,0.3,1) both',
        maxWidth: '400px',
        width: '100%',
      }}
    >
      <span
        style={{
          flex: 1,
          fontSize: '13px',
          fontWeight: 500,
          color: style.color,
          lineHeight: 1.4,
        }}
      >
        {message}
      </span>

      {action && (
        <button
          type="button"
          onClick={() => { action.onClick(); onDismiss(); }}
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            border: 'none',
            background: style.color,
            color: '#fff',
            fontSize: '11px',
            fontWeight: 600,
            fontFamily: 'var(--font-body)',
            cursor: 'pointer',
            flexShrink: 0,
            transition: 'opacity 160ms ease',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
        >
          {action.label}
        </button>
      )}

      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '20px',
          height: '20px',
          borderRadius: '6px',
          border: 'none',
          background: 'transparent',
          color: style.color,
          cursor: 'pointer',
          flexShrink: 0,
          opacity: 0.6,
          transition: 'opacity 120ms ease',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '0.6'; }}
      >
        <X size={13} />
      </button>
    </div>
  );
}

export interface ToastItem {
  id: string;
  message: string;
  variant: ToastProps['variant'];
  action?: { label: string; onClick: () => void };
  duration?: number;
}

export function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        pointerEvents: 'none',
      }}
    >
      {toasts.map(t => (
        <div key={t.id} style={{ pointerEvents: 'auto' }}>
          <Toast
            message={t.message}
            variant={t.variant}
            onDismiss={() => onDismiss(t.id)}
            action={t.action}
            duration={t.duration}
          />
        </div>
      ))}
    </div>
  );
}
