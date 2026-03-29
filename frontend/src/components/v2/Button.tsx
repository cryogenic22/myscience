import React, { useState } from 'react';

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'accent';
  size?: 'sm' | 'md';
  children?: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
  style?: React.CSSProperties;
  'aria-label'?: string;
}

export default function Button({
  variant = 'primary',
  size = 'md',
  children,
  icon,
  onClick,
  disabled = false,
  title,
  style: styleProp,
  'aria-label': ariaLabel,
}: ButtonProps) {
  const [hovered, setHovered] = useState(false);
  const [active, setActive] = useState(false);

  const isSm = size === 'sm';
  const padding = isSm ? 'var(--space-1) var(--space-3)' : 'var(--space-2) var(--space-5)';
  const fontSize = isSm ? 'var(--text-sm)' : 'var(--text-base)';

  let bg: string;
  let color: string;
  let border: string;

  if (variant === 'primary' || variant === 'accent') {
    bg = disabled
      ? 'var(--text-tertiary)'
      : active
        ? '#1d4ed8'
        : hovered
          ? '#3b82f6'
          : 'var(--accent)';
    color = '#ffffff';
    border = 'none';
  } else if (variant === 'secondary') {
    bg = hovered && !disabled ? 'var(--accent-soft)' : 'transparent';
    color = disabled ? 'var(--text-tertiary)' : 'var(--accent)';
    border = `1px solid ${disabled ? 'var(--text-tertiary)' : 'var(--accent)'}`;
  } else {
    /* ghost */
    bg = hovered && !disabled ? 'var(--accent-soft)' : 'transparent';
    color = disabled ? 'var(--text-tertiary)' : 'var(--accent)';
    border = 'none';
  }

  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-2)',
        fontFamily: 'var(--font-body)',
        fontSize,
        fontWeight: 500,
        lineHeight: 1,
        padding,
        borderRadius: 'var(--radius-md)',
        backgroundColor: bg,
        color,
        border,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        transition: `all var(--duration-fast) var(--ease-out)`,
        outline: 'none',
        ...styleProp,
      }}
    >
      {icon}
      {children}
    </button>
  );
}
