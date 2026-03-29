/**
 * Toolbar — 48px top bar for the three-zone workspace.
 * Left: Logo text in Fraunces. Center: Search input with typeahead. Right: Settings + theme toggle.
 */

import { useState, useCallback, useRef } from 'react';
import { useTheme } from '../../hooks/useTheme';
import SearchDropdown from './SearchDropdown';
import Button from './Button';

interface SuggestionItem {
  entity_id: string;
  entity_type: string;
  label: string;
  similarity: number;
}

interface ToolbarProps {
  onSearch: (query: string) => void;
  onSearchChange?: (value: string) => void;
  onSearchSelect?: (suggestion: { entity_id: string; entity_type: string; label: string }) => void;
  suggestions?: SuggestionItem[];
  suggestionsLoading?: boolean;
  lens?: 'explore' | 'curate';
  onLensChange?: (lens: 'explore' | 'curate') => void;
}

export default function Toolbar({
  onSearch,
  onSearchChange,
  onSearchSelect,
  suggestions,
  suggestionsLoading,
  lens,
  onLensChange,
}: ToolbarProps) {
  const { theme, toggleTheme } = useTheme();
  const [searchValue, setSearchValue] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  const showDropdown =
    searchValue.trim().length >= 2 &&
    (suggestionsLoading || (suggestions && suggestions.length > 0));

  const handleChange = useCallback(
    (value: string) => {
      setSearchValue(value);
      setSelectedIndex(-1);
      onSearchChange?.(value);
    },
    [onSearchChange],
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (
        selectedIndex >= 0 &&
        suggestions &&
        selectedIndex < suggestions.length &&
        onSearchSelect
      ) {
        const s = suggestions[selectedIndex];
        onSearchSelect({ entity_id: s.entity_id, entity_type: s.entity_type, label: s.label });
        setSearchValue('');
        setSelectedIndex(-1);
        onSearchChange?.('');
        return;
      }
      const trimmed = searchValue.trim();
      if (trimmed) {
        onSearch(trimmed);
        setSearchValue('');
        setSelectedIndex(-1);
        onSearchChange?.('');
      }
    },
    [searchValue, onSearch, onSearchChange, onSearchSelect, suggestions, selectedIndex],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const count = suggestions?.length ?? 0;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1 >= count ? 0 : prev + 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 < 0 ? count - 1 : prev - 1));
        return;
      }
      if (e.key === 'Escape') {
        setSelectedIndex(-1);
        onSearchChange?.('');
        setSearchValue('');
        inputRef.current?.blur();
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (
          selectedIndex >= 0 &&
          suggestions &&
          selectedIndex < suggestions.length &&
          onSearchSelect
        ) {
          const s = suggestions[selectedIndex];
          onSearchSelect({ entity_id: s.entity_id, entity_type: s.entity_type, label: s.label });
          setSearchValue('');
          setSelectedIndex(-1);
          onSearchChange?.('');
        } else {
          const trimmed = searchValue.trim();
          if (trimmed) {
            onSearch(trimmed);
            setSearchValue('');
            setSelectedIndex(-1);
            onSearchChange?.('');
          }
        }
      }
    },
    [searchValue, suggestions, selectedIndex, onSearch, onSearchChange, onSearchSelect],
  );

  const handleDropdownSelect = useCallback(
    (suggestion: { entity_id: string; entity_type: string; label: string }) => {
      onSearchSelect?.(suggestion);
      setSearchValue('');
      setSelectedIndex(-1);
      onSearchChange?.('');
    },
    [onSearchSelect, onSearchChange],
  );

  const handleDropdownClose = useCallback(() => {
    setSelectedIndex(-1);
    onSearchChange?.('');
  }, [onSearchChange]);

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
              zIndex: 1,
            }}
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            data-search-input
            type="text"
            value={searchValue}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search entities, ask a question..."
            autoComplete="off"
            style={{
              width: '100%',
              paddingLeft: 'var(--space-8)',
              paddingRight: 'var(--space-3)',
              height: 32,
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--font-body)',
              border: '1px solid rgba(0,0,0,0.08)',
              borderRadius: 'var(--radius-full)',
              backgroundColor: 'var(--surface-secondary)',
              color: 'var(--text-primary)',
              outline: 'none',
              transition: `border-color var(--duration-fast) ease`,
            }}
            onFocus={(e) => {
              (e.target as HTMLElement).style.borderColor = 'var(--accent)';
            }}
            onBlur={(e) => {
              (e.target as HTMLElement).style.borderColor = 'rgba(0,0,0,0.08)';
            }}
          />

          {/* Typeahead dropdown */}
          {showDropdown && (
            <SearchDropdown
              suggestions={suggestions ?? []}
              isLoading={suggestionsLoading ?? false}
              selectedIndex={selectedIndex}
              onSelect={handleDropdownSelect}
              onClose={handleDropdownClose}
            />
          )}
        </div>
      </form>

      {/* Right: Settings + Theme Toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexShrink: 0 }}>
        {/* Cmd+K hint */}
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
            opacity: 0.6,
            flexShrink: 0,
          }}
        >
          {navigator.platform?.includes('Mac') ? '\u2318K' : 'Ctrl+K'}
        </span>

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
