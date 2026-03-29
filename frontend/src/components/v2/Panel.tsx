import React from 'react';

interface PanelProps {
  side: 'left' | 'right';
  width?: number;
  collapsed?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
}

export default function Panel({
  side,
  width = 360,
  collapsed = false,
  onToggle,
  children,
}: PanelProps) {
  const isLeft = side === 'left';

  return (
    <div
      style={{
        position: 'relative',
        width: collapsed ? 0 : width,
        minWidth: collapsed ? 0 : width,
        height: '100%',
        overflow: 'hidden',
        backgroundColor: 'var(--surface-elevated)',
        borderRight: isLeft && !collapsed ? '1px solid var(--surface-secondary)' : undefined,
        borderLeft: !isLeft && !collapsed ? '1px solid var(--surface-secondary)' : undefined,
        transition: `width var(--duration-slow) var(--ease-out), min-width var(--duration-slow) var(--ease-out)`,
        boxShadow: collapsed ? 'none' : 'var(--shadow-sm)',
      }}
    >
      {/* Toggle button */}
      {onToggle && (
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
          style={{
            position: 'absolute',
            top: 'var(--space-3)',
            [isLeft ? 'right' : 'left']: collapsed ? -28 : 'var(--space-2)',
            zIndex: 10,
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--surface-secondary)',
            backgroundColor: 'var(--surface-elevated)',
            cursor: 'pointer',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            transition: `all var(--duration-fast) var(--ease-out)`,
          }}
        >
          {collapsed
            ? (isLeft ? '\u203A' : '\u2039')
            : (isLeft ? '\u2039' : '\u203A')}
        </button>
      )}

      {/* Panel content */}
      <div
        style={{
          height: '100%',
          overflow: 'auto',
          opacity: collapsed ? 0 : 1,
          transition: `opacity var(--duration-normal) var(--ease-out)`,
          padding: collapsed ? 0 : 'var(--space-4)',
        }}
      >
        {children}
      </div>
    </div>
  );
}
