import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Building2,
  Dna,
  FileText,
  FlaskConical,
  Network,
  Pill as PillIcon,
  Search,
  Target,
} from 'lucide-react';
import { api, type SearchSuggestion } from '../../api';
import { displayName } from '../../brand';
import { NODE_COLORS } from './graph-constants';

/** Picked entity shape shared across the explorer's search affordances. */
export interface PickedEntity {
  id: string;
  type: string;
  label: string;
}

const TYPE_ICONS: Record<string, ReactNode> = {
  drug: <PillIcon size={14} />,
  company: <Building2 size={14} />,
  trial: <FlaskConical size={14} />,
  mechanism: <Dna size={14} />,
  therapeutic_area: <Target size={14} />,
  literature: <FileText size={14} />,
};

function typeIcon(type: string): ReactNode {
  return TYPE_ICONS[type] ?? <Network size={14} />;
}

function typeColor(type: string): string {
  return NODE_COLORS[type] ?? NODE_COLORS.unknown ?? '#64748b';
}

interface EntitySearchProps {
  /** Called when the user picks a suggestion. */
  onPick: (entity: PickedEntity) => void;
  /**
   * Called when the user edits the text AWAY from an already-committed
   * selection (`selected` + `value`). The committed entity is now stale — the
   * parent must drop it so a query can't run against a hidden, stale id while
   * the box shows different text. (MZ-XR-20260615-001)
   */
  onClearSelection?: () => void;
  placeholder?: string;
  /** Controlled query text (e.g. to reflect the active anchor label). */
  value?: string;
  /** Visually flag that a selection has been committed (path From/To). */
  selected?: boolean;
  /** Compact variant used inside the path-finder panel. */
  compact?: boolean;
  /** Max suggestions to request/show. */
  limit?: number;
  autoFocus?: boolean;
}

/**
 * One shared, debounced entity search backed by `api.searchSuggest` (trigram
 * over ALL entity types). Replaces the three byte-identical 5-call fan-out
 * inputs that previously lived in GraphExplorer.
 */
export default function EntitySearch({
  onPick,
  onClearSelection,
  placeholder = 'Search a drug, company, trial, mechanism, or therapeutic area...',
  value,
  selected = false,
  compact = false,
  limit = 12,
  autoFocus = false,
}: EntitySearchProps) {
  const [query, setQuery] = useState(value ?? '');
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const timeoutRef = useRef<number>(0);

  // Keep the input in sync when a parent commits a label. Only push NON-empty
  // committed values: a parent clearing its selection (value → '') must not wipe
  // the text the user is actively typing to choose a replacement.
  useEffect(() => {
    if (value) setQuery(value);
  }, [value]);

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const handleChange = useCallback((next: string) => {
    setQuery(next);
    // The user is editing. If a selection was already committed and the text now
    // diverges from it, that committed entity is stale — drop it so a query can't
    // run against a hidden id that no longer matches the box. (MZ-XR-20260615-001)
    if (selected && next !== value) {
      onClearSelection?.();
    }
    clearTimeout(timeoutRef.current);
    if (next.trim().length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    timeoutRef.current = window.setTimeout(async () => {
      try {
        const res = await api.searchSuggest(next.trim(), limit);
        const items = res.suggestions ?? [];
        setSuggestions(items.slice(0, limit));
        setShowSuggestions(items.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 220);
  }, [limit, selected, value, onClearSelection]);

  const handlePick = useCallback((s: SearchSuggestion) => {
    onPick({ id: s.entity_id, type: s.entity_type, label: s.label });
    setQuery(s.label);
    setShowSuggestions(false);
    setSuggestions([]);
  }, [onPick]);

  const iconSize = compact ? 13 : 16;
  const inputHeight = compact ? '36px' : '48px';

  return (
    <div className="relative">
      <Search
        className="absolute text-ink-4"
        size={iconSize}
        style={{ left: compact ? '10px' : '14px', top: compact ? '11px' : '15px' }}
      />
      <input
        value={query}
        autoFocus={autoFocus}
        onChange={(event) => handleChange(event.target.value)}
        onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
        onBlur={() => window.setTimeout(() => setShowSuggestions(false), 150)}
        placeholder={placeholder}
        className="input-surface w-full rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-brand/15"
        style={{
          height: inputHeight,
          padding: compact ? '0 10px 0 32px' : '8px 16px 8px 40px',
          fontSize: compact ? '12px' : '14px',
          border: selected
            ? '1.5px solid var(--color-accent, #2563eb)'
            : '1px solid var(--color-line, #e2e8f0)',
        }}
      />
      {showSuggestions && (
        <div
          className="animate-fade-in absolute left-0 right-0 top-full mt-2 overflow-hidden rounded-lg border border-line bg-white/96 shadow-xl"
          style={{ zIndex: 30, maxHeight: '260px', overflowY: 'auto' }}
        >
          {suggestions.map((s) => (
            <button
              key={`${s.entity_type}:${s.entity_id}`}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handlePick(s)}
              className="flex w-full items-center gap-3 text-left transition-colors hover:bg-surface-2"
              style={{ padding: compact ? '8px 12px' : '12px 16px' }}
            >
              <span className="rounded-sm bg-surface-3 text-ink-3" style={{ padding: compact ? '4px' : '6px' }}>
                {typeIcon(s.entity_type)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-ink" style={{ fontSize: compact ? '12px' : '14px' }}>
                  {s.label}
                </div>
              </div>
              <span
                className="shrink-0 rounded-full text-[10px] font-medium capitalize"
                style={{
                  padding: '2px 8px',
                  color: typeColor(s.entity_type),
                  background: 'color-mix(in srgb, currentColor 12%, transparent)',
                }}
              >
                {displayName(s.entity_type)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
