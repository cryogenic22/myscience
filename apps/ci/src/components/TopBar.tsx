export function TopBar() {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 5,
        background: 'color-mix(in oklab, var(--mz-color-canvas) 88%, transparent)',
        backdropFilter: 'saturate(140%) blur(8px)',
        borderBottom: '1px solid var(--mz-color-border-subtle)',
        padding: 'var(--mz-space-3) var(--mz-space-6)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--mz-space-3)',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--mz-font-mono)',
          fontSize: 'var(--mz-text-mono-2)',
          color: 'var(--mz-color-text-tertiary)',
          letterSpacing: 'var(--mz-tracking-wide)',
        }}
      >
        TUE 28 APR · 09:14
      </span>
      <div style={{ flex: 1 }} />
      <button
        type="button"
        style={{
          appearance: 'none',
          background: 'var(--mz-color-elevated)',
          border: '1px solid var(--mz-color-border-subtle)',
          borderRadius: 'var(--mz-radius-control)',
          padding: '6px 10px',
          color: 'var(--mz-color-text-secondary)',
          fontFamily: 'var(--mz-font-sans)',
          fontSize: 'var(--mz-text-body-3)',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        Search
        <kbd
          style={{
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            background: 'var(--mz-color-surface)',
            border: '1px solid var(--mz-color-border-subtle)',
            borderRadius: 4,
            padding: '0 4px',
          }}
        >
          ⌘K
        </kbd>
      </button>
    </header>
  );
}
