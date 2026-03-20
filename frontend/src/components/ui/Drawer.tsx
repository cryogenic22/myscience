import { X } from 'lucide-react';
import { type ReactNode, useEffect } from 'react';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  width?: string;
}

export function Drawer({ isOpen, onClose, title, subtitle, children, width }: DrawerProps) {
  const resolvedWidth = width ?? 'clamp(360px, 42vw, 640px)';

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        style={{ background: 'rgba(10,10,11,0.12)', backdropFilter: 'blur(2px)' }}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed inset-y-0 right-0 z-50 flex flex-col animate-slide-in"
        style={{
          width: resolvedWidth,
          maxWidth: '94vw',
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-line)',
          boxShadow: 'var(--shadow-xl)',
        }}
      >
        {/* Header */}
        <div
          className="shrink-0 flex items-start justify-between p-6"
          style={{ borderBottom: '1px solid var(--color-line)' }}
        >
          <div>
            <h2
              style={{
                fontSize: '16px',
                fontWeight: 600,
                color: 'var(--color-ink)',
                letterSpacing: '-0.02em',
                lineHeight: 1.3,
              }}
            >
              {title}
            </h2>
            {subtitle && (
              <p
                style={{
                  fontSize: '12px',
                  color: 'var(--color-ink-4)',
                  marginTop: '3px',
                  fontFamily: 'var(--font-body)',
                }}
              >
                {subtitle}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-icon shrink-0 ml-4"
            aria-label="Close"
          >
            <X size={15} />
          </button>
        </div>

        {/* Scrollable content */}
        <div
          className="flex-1 overflow-y-auto p-6"
          style={{ minHeight: 0 }}
        >
          {children}
        </div>
      </div>
    </>
  );
}
