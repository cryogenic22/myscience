export type CISurface = 'digest' | 'watchlist' | 'alerts' | 'reviewer' | 'briefs' | 'trackers' | 'health';

interface SidebarProps {
  active: CISurface;
  onChange: (s: CISurface) => void;
}

const PRIMARY: Array<{ id: CISurface; label: string; hint?: string }> = [
  { id: 'digest',    label: 'Daily Digest',    hint: 'D' },
  { id: 'watchlist', label: 'Watchlist',       hint: 'W' },
  { id: 'reviewer',  label: 'Reviewer Queue',  hint: 'R' },
  { id: 'alerts',    label: 'Alerts',          hint: 'A' },
];

const SECONDARY: Array<{ id: CISurface; label: string; phase: string }> = [
  { id: 'briefs',   label: 'Briefs',           phase: '1.5' },
  { id: 'trackers', label: 'Trackers',         phase: '1.5' },
  { id: 'health',   label: 'Connector Health', phase: '1.5' },
];

export function Sidebar({ active, onChange }: SidebarProps) {
  return (
    <aside
      style={{
        background: 'var(--mz-color-surface)',
        borderRight: '1px solid var(--mz-color-border-subtle)',
        padding: 'var(--mz-space-4) var(--mz-space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--mz-space-6)',
        position: 'sticky',
        top: 0,
        height: '100vh',
        overflow: 'auto',
      }}
    >
      <a
        href="/"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--mz-space-2)',
          padding: 'var(--mz-space-2)',
          borderRadius: 'var(--mz-radius-control)',
          color: 'var(--mz-color-text-primary)',
          textDecoration: 'none',
          fontFamily: 'var(--mz-font-display)',
          fontWeight: 'var(--mz-weight-semibold)',
          letterSpacing: 'var(--mz-tracking-tight)',
        }}
      >
        <span
          aria-hidden
          style={{
            width: 14,
            height: 14,
            borderRadius: 4,
            background: 'var(--mz-color-accent)',
          }}
        />
        <span>Market Zero</span>
        <span
          style={{
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            color: 'var(--mz-color-accent)',
            letterSpacing: 'var(--mz-tracking-wide)',
            marginLeft: 'var(--mz-space-1)',
          }}
        >
          · CI
        </span>
      </a>

      <NavGroup label="Workflow">
        {PRIMARY.map((item) => (
          <NavItem
            key={item.id}
            label={item.label}
            active={active === item.id}
            hint={item.hint}
            onClick={() => onChange(item.id)}
          />
        ))}
      </NavGroup>

      <NavGroup label="Coming next">
        {SECONDARY.map((item) => (
          <NavItem
            key={item.id}
            label={item.label}
            active={active === item.id}
            phase={item.phase}
            onClick={() => onChange(item.id)}
          />
        ))}
      </NavGroup>

      <div style={{ marginTop: 'auto', fontSize: 'var(--mz-text-mono-3)', color: 'var(--mz-color-text-tertiary)', fontFamily: 'var(--mz-font-mono)', letterSpacing: 'var(--mz-tracking-wide)' }}>
        v0.1.0 · phase 0
      </div>
    </aside>
  );
}

function NavGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--mz-space-1)' }}>
      <div
        style={{
          fontFamily: 'var(--mz-font-mono)',
          fontSize: 'var(--mz-text-mono-3)',
          color: 'var(--mz-color-text-tertiary)',
          letterSpacing: 'var(--mz-tracking-wide)',
          textTransform: 'uppercase',
          padding: '0 var(--mz-space-2)',
          marginBottom: 'var(--mz-space-1)',
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

interface NavItemProps {
  label: string;
  active: boolean;
  onClick: () => void;
  hint?: string;
  phase?: string;
}

function NavItem({ label, active, onClick, hint, phase }: NavItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        appearance: 'none',
        background: active ? 'var(--mz-color-elevated)' : 'transparent',
        border: 'none',
        textAlign: 'left',
        padding: 'var(--mz-space-2) var(--mz-space-2)',
        borderRadius: 'var(--mz-radius-control)',
        color: active ? 'var(--mz-color-text-primary)' : 'var(--mz-color-text-secondary)',
        fontFamily: 'var(--mz-font-sans)',
        fontSize: 'var(--mz-text-body-2)',
        fontWeight: active ? 'var(--mz-weight-semibold)' : 'var(--mz-weight-medium)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        transition: 'background var(--mz-duration-fast) var(--mz-ease-standard)',
        position: 'relative',
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--mz-space-2)' }}>
        {active && (
          <span
            aria-hidden
            style={{
              width: 3,
              height: 16,
              background: 'var(--mz-color-accent)',
              borderRadius: 2,
              position: 'absolute',
              left: -8,
            }}
          />
        )}
        {label}
      </span>
      {hint && (
        <kbd
          style={{
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            color: 'var(--mz-color-text-tertiary)',
            background: 'var(--mz-color-elevated)',
            border: '1px solid var(--mz-color-border-subtle)',
            borderRadius: 4,
            padding: '0 4px',
          }}
        >
          {hint}
        </kbd>
      )}
      {phase && (
        <span
          style={{
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            color: 'var(--mz-color-text-tertiary)',
            letterSpacing: 'var(--mz-tracking-wide)',
          }}
        >
          P{phase}
        </span>
      )}
    </button>
  );
}
