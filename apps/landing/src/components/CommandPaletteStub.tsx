import { useEffect, useRef, useState } from 'react';

interface CommandPaletteStubProps {
  onClose: () => void;
}

interface Command {
  id: string;
  label: string;
  hint: string;
  run: () => void;
}

/**
 * Phase 0 ⌘K stub. Real palette (with cross-module search, fuzzy match,
 * scoped commands per module) lands in Phase 1 sprint C1.
 */
export function CommandPaletteStub({ onClose }: CommandPaletteStubProps) {
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const commands: Command[] = [
    { id: 'open-ci',         label: 'Open Competitive Intelligence',  hint: 'CI · MODULE',     run: () => (window.location.href = '/ci') },
    { id: 'open-research',   label: 'Open Pharma Research',           hint: 'RESEARCH · MODULE', run: () => (window.location.href = '/research') },
    { id: 'search-pfizer',   label: 'Search "Pfizer"',                hint: 'CROSS-MODULE',    run: () => alert('search wiring lands in C1') },
    { id: 'open-watchlist',  label: 'Open my Watchlist',              hint: 'CI',              run: () => (window.location.href = '/ci/watchlist') },
    { id: 'new-brief',       label: 'Compose new brief',              hint: 'CI',              run: () => (window.location.href = '/ci/briefs/new') },
    { id: 'platform-health', label: 'View platform health',           hint: 'PLATFORM',        run: () => alert('admin surface lands in C8') },
  ];

  const visible = commands.filter((c) =>
    c.label.toLowerCase().includes(q.toLowerCase()) ||
    c.hint.toLowerCase().includes(q.toLowerCase()),
  );

  return (
    <div
      role="dialog"
      aria-modal
      aria-label="Command palette"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in oklab, var(--mz-color-canvas) 60%, transparent)',
        backdropFilter: 'blur(8px) saturate(140%)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '15vh',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, 92vw)',
          background: 'var(--mz-color-surface)',
          border: '1px solid var(--mz-color-border-subtle)',
          borderRadius: 'var(--mz-radius-elevated)',
          boxShadow: 'var(--mz-shadow-lg)',
          overflow: 'hidden',
        }}
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search modules, signals, commands…"
          style={{
            width: '100%',
            border: 'none',
            outline: 'none',
            background: 'transparent',
            color: 'var(--mz-color-text-primary)',
            fontFamily: 'var(--mz-font-sans)',
            fontSize: 'var(--mz-text-headline-3)',
            padding: 'var(--mz-space-4) var(--mz-space-6)',
            borderBottom: '1px solid var(--mz-color-border-subtle)',
          }}
        />
        <ul role="listbox" style={{ listStyle: 'none', margin: 0, padding: 'var(--mz-space-2) 0', maxHeight: 380, overflow: 'auto' }}>
          {visible.length === 0 && (
            <li style={{ padding: 'var(--mz-space-4) var(--mz-space-6)', color: 'var(--mz-color-text-tertiary)', fontSize: 'var(--mz-text-body-3)' }}>
              No matches.
            </li>
          )}
          {visible.map((c) => (
            <li
              key={c.id}
              role="option"
              tabIndex={0}
              onClick={() => { c.run(); onClose(); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { c.run(); onClose(); } }}
              style={{
                padding: 'var(--mz-space-3) var(--mz-space-6)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
                fontSize: 'var(--mz-text-body-2)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--mz-color-elevated)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span>{c.label}</span>
              <span
                style={{
                  fontFamily: 'var(--mz-font-mono)',
                  fontSize: 'var(--mz-text-mono-3)',
                  color: 'var(--mz-color-text-tertiary)',
                  letterSpacing: 'var(--mz-tracking-wide)',
                }}
              >
                {c.hint}
              </span>
            </li>
          ))}
        </ul>
        <div
          style={{
            padding: 'var(--mz-space-2) var(--mz-space-6)',
            borderTop: '1px solid var(--mz-color-border-subtle)',
            background: 'var(--mz-color-elevated)',
            color: 'var(--mz-color-text-tertiary)',
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            letterSpacing: 'var(--mz-tracking-wide)',
            display: 'flex',
            gap: 'var(--mz-space-4)',
          }}
        >
          <span>↵ Run</span>
          <span>↑↓ Navigate</span>
          <span>ESC Close</span>
        </div>
      </div>
    </div>
  );
}
