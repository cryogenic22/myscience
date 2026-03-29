/**
 * SearchDropdown — Typeahead suggestion overlay for Toolbar search.
 * Positioned absolutely below the search input.
 */

import { useEffect, useRef } from 'react';
import EntityDot from './EntityDot';
import Badge from './Badge';

interface Suggestion {
  entity_id: string;
  entity_type: string;
  label: string;
  similarity: number;
}

interface SearchDropdownProps {
  suggestions: Suggestion[];
  isLoading: boolean;
  selectedIndex: number;
  onSelect: (suggestion: { entity_id: string; entity_type: string; label: string }) => void;
  onClose: () => void;
}

export default function SearchDropdown({
  suggestions,
  isLoading,
  selectedIndex,
  onSelect,
  onClose,
}: SearchDropdownProps) {
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current && selectedIndex >= 0) {
      const items = listRef.current.querySelectorAll('[data-suggestion-item]');
      items[selectedIndex]?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (listRef.current && !listRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  if (!isLoading && suggestions.length === 0) {
    return (
      <div
        style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          marginTop: 4,
          background: 'var(--surface-elevated)',
          border: '1px solid rgba(0,0,0,0.1)',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 100,
          padding: 'var(--space-4)',
          textAlign: 'center',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-sm)',
          color: 'var(--text-tertiary)',
        }}
      >
        No results
      </div>
    );
  }

  return (
    <div
      ref={listRef}
      style={{
        position: 'absolute',
        top: '100%',
        left: 0,
        right: 0,
        marginTop: 4,
        background: 'var(--surface-elevated)',
        border: '1px solid rgba(0,0,0,0.1)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-lg)',
        zIndex: 100,
        maxHeight: 320,
        overflowY: 'auto',
      }}
    >
      {isLoading && suggestions.length === 0 ? (
        <div
          style={{
            padding: 'var(--space-4)',
            textAlign: 'center',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-sm)',
            color: 'var(--text-tertiary)',
          }}
        >
          Searching...
        </div>
      ) : (
        suggestions.map((s, i) => (
          <div
            key={s.entity_id}
            data-suggestion-item
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect({ entity_id: s.entity_id, entity_type: s.entity_type, label: s.label });
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              padding: 'var(--space-2) var(--space-3)',
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-primary)',
              background: i === selectedIndex ? 'var(--accent-soft)' : 'transparent',
              transition: `background var(--duration-fast) ease`,
            }}
            onMouseEnter={(e) => {
              if (i !== selectedIndex) {
                (e.currentTarget as HTMLElement).style.background = 'var(--surface-secondary)';
              }
            }}
            onMouseLeave={(e) => {
              if (i !== selectedIndex) {
                (e.currentTarget as HTMLElement).style.background = 'transparent';
              }
            }}
          >
            <EntityDot type={s.entity_type} size="sm" />
            <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {s.label}
            </span>
            <Badge label={s.entity_type} />
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
                flexShrink: 0,
              }}
            >
              {Math.round(s.similarity * 100)}%
            </span>
          </div>
        ))
      )}
    </div>
  );
}
