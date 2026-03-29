/**
 * Toolbar — 48px top bar for the three-zone workspace.
 * Left: Logo text in Fraunces. Center: Search input. Right: Settings + theme toggle.
 */

import { useState, useCallback } from 'react';
import { useTheme } from '../../hooks/useTheme';
import Input from './Input';
import Button from './Button';

interface ToolbarProps {
  onSearch: (query: string) => void;
  lens?: 'explore' | 'curate';
  onLensChange?: (lens: 'explore' | 'curate') => void;
}

export default function Toolbar({ onSearch, lens, onLensChange }: ToolbarProps) {
  const { theme, toggleTheme } = useTheme();
  const [searchValue, setSearchValue] = useState('');

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = searchValue.trim();
      if (trimmed) {
        onSearch(trimmed);
      }
    },
    [searchValue, onSearch],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        const trimmed = searchValue.trim();
        if (trimmed) {
          onSearch(trimmed);
        }
      }
    },
    [searchValue, onSearch],
  );

  return (
    <header
      style={{
        height: 48,
        minHeight: 48,
        maxHeight: 48,
        background: 'var(--surface-elevated)',
        borderBottom: '1px solid rgba(0,0,0,0.06)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        padding: '0 var(--space-4)',
        fontFamily: 'var(--font-body)',
        flexShrink: 0,
      }}
    >
      {/* Left: Logo */}
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-base)',
          fontWeight: 300,
          color: 'var(--text-tertiary)',
          letterSpacing: '-0.01em',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
      >
        Market Zero
      </span>

      {/* Lens toggle (optional) */}
      {lens && onLensChange && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-1)',
            background: 'var(--surface-inset)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-1)',
            flexShrink: 0,
          }}
        >
          {(['explore', 'curate'] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => onLensChange(l)}
              style={{
                padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-body)',
                fontWeight: 500,
                cursor: 'pointer',
                background: lens === l ? 'var(--surface-elevated)' : 'transparent',
                color: lens === l ? 'var(--text-primary)' : 'var(--text-tertiary)',
                boxShadow: lens === l ? 'var(--shadow-xs)' : 'none',
                transition: `all var(--duration-fast) ease`,
              }}
            >
              {l === 'explore' ? 'Explore' : 'Curate'}
            </button>
          ))}
        </div>
      )}

      {/* Center: Search */}
      <form
        onSubmit={handleSubmit}
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          minWidth: 0,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            width: '100%',
            maxWidth: 480,
            margin: '0 auto',
            position: 'relative',
          }}
        >
          {/* Search icon */}
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{
              position: 'absolute',
              left: 'var(--space-3)',
              color: 'var(--text-quaternary)',
              pointerEvents: 'none',
              flexShrink: 0,
            }}
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <Input
            variant="search"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search entities, ask a question..."
            style={{
              paddingLeft: 'var(--space-8)',
              height: 32,
              fontSize: 'var(--text-sm)',
            }}
          />
        </div>
      </form>

      {/* Right: Settings + Theme Toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexShrink: 0 }}>
        {/* Settings icon */}
        <Button
          variant="ghost"
          size="sm"
          title="Settings"
          aria-label="Settings"
          icon={
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          }
        />

        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
          icon={
            theme === 'dark' ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2" />
                <path d="M12 20v2" />
                <path d="m4.93 4.93 1.41 1.41" />
                <path d="m17.66 17.66 1.41 1.41" />
                <path d="M2 12h2" />
                <path d="M20 12h2" />
                <path d="m6.34 17.66-1.41 1.41" />
                <path d="m19.07 4.93-1.41 1.41" />
              </svg>
            ) : (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
              </svg>
            )
          }
        />
      </div>
    </header>
  );
}
