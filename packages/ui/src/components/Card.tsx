import type { ReactNode, HTMLAttributes } from 'react';

export type CardVariant = 'flat' | 'elevated' | 'interactive';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  /** Render the card as a button-like surface (keyboard + ARIA). */
  interactive?: boolean;
  children: ReactNode;
}

/**
 * Card — single composition primitive used everywhere a surface needs
 * a contained, separated visual treatment. Variants:
 *
 * - `flat`        — subtle border on `surface`. The default.
 * - `elevated`    — `elevated` background + small shadow. Use sparingly.
 * - `interactive` — flat + cursor + hover state. Use when the whole card
 *                   is clickable; pair with `interactive` prop for ARIA.
 *
 * No tailwind utilities; CSS variables only.
 */
export function Card({
  variant = 'flat',
  interactive = false,
  children,
  style,
  onClick,
  onKeyDown,
  ...rest
}: CardProps) {
  const isInteractive = variant === 'interactive' || interactive;

  const base: React.CSSProperties = {
    background: variant === 'elevated' ? 'var(--mz-color-elevated)' : 'var(--mz-color-surface)',
    borderRadius: variant === 'elevated' ? 'var(--mz-radius-elevated)' : 'var(--mz-radius-card)',
    border: `1px solid ${variant === 'elevated' ? 'transparent' : 'var(--mz-color-border-subtle)'}`,
    boxShadow: variant === 'elevated' ? 'var(--mz-shadow-md)' : 'none',
    padding: 'var(--mz-density-padding)',
    transition: `background var(--mz-duration-fast) var(--mz-ease-standard), border-color var(--mz-duration-fast) var(--mz-ease-standard), box-shadow var(--mz-duration-fast) var(--mz-ease-standard)`,
    color: 'var(--mz-color-text-primary)',
    ...style,
  };

  if (isInteractive) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick?.(e as never);
          }
          onKeyDown?.(e);
        }}
        className="mz-card mz-card--interactive"
        style={base}
        {...rest}
      >
        {children}
      </div>
    );
  }

  return (
    <div className={`mz-card mz-card--${variant}`} style={base} {...rest}>
      {children}
    </div>
  );
}
