interface HeaderProps {
  onOpenPalette: () => void;
}

export function Header({ onOpenPalette }: HeaderProps) {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        background: 'color-mix(in oklab, var(--mz-color-canvas) 88%, transparent)',
        backdropFilter: 'saturate(140%) blur(8px)',
        borderBottom: '1px solid var(--mz-color-border-subtle)',
      }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: '0 auto',
          padding: 'var(--mz-space-3) var(--mz-space-6)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--mz-space-4)',
        }}
      >
        <Wordmark />
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={onOpenPalette}
          aria-label="Open command palette"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--mz-space-2)',
            padding: '6px 10px 6px 12px',
            background: 'var(--mz-color-elevated)',
            color: 'var(--mz-color-text-secondary)',
            border: '1px solid var(--mz-color-border-subtle)',
            borderRadius: 'var(--mz-radius-control)',
            fontFamily: 'var(--mz-font-sans)',
            fontSize: 'var(--mz-text-body-3)',
            cursor: 'pointer',
            transition: 'all var(--mz-duration-fast) var(--mz-ease-standard)',
          }}
        >
          <span>Search</span>
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
        <UserChip />
      </div>
    </header>
  );
}

function Wordmark() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--mz-space-2)' }}>
      <span
        aria-hidden
        style={{
          width: 16,
          height: 16,
          borderRadius: 4,
          background:
            'conic-gradient(from 90deg at 50% 50%, var(--mz-color-info), var(--mz-color-success), var(--mz-color-warning), var(--mz-color-info))',
          opacity: 0.85,
        }}
      />
      <span
        style={{
          fontFamily: 'var(--mz-font-display)',
          fontWeight: 'var(--mz-weight-semibold)',
          letterSpacing: 'var(--mz-tracking-tight)',
          fontSize: 'var(--mz-text-headline-3)',
        }}
      >
        PulseAction<span style={{ color: 'var(--mz-color-text-tertiary)', fontWeight: 'var(--mz-weight-medium)' }}>.AI</span>
      </span>
    </div>
  );
}

function UserChip() {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '4px 10px 4px 4px',
        borderRadius: 'var(--mz-radius-pill)',
        background: 'var(--mz-color-elevated)',
        border: '1px solid var(--mz-color-border-subtle)',
        fontSize: 'var(--mz-text-body-3)',
        color: 'var(--mz-color-text-secondary)',
      }}
    >
      <span
        aria-hidden
        style={{
          width: 22,
          height: 22,
          borderRadius: '50%',
          background:
            'linear-gradient(135deg, var(--mz-color-info), var(--mz-color-success))',
          color: 'white',
          fontFamily: 'var(--mz-font-mono)',
          fontSize: 11,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 600,
        }}
      >
        K
      </span>
      kapil@…
    </div>
  );
}
