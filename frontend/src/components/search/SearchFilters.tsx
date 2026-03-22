import {
  Pill,
  FlaskConical,
  BookOpen,
  Building2,
  Target,
  Filter,
} from 'lucide-react';
import {
  ENTITY_TYPES,
  VIEW_OPTIONS,
  SORT_OPTIONS,
  type SearchViewMode,
  type SortMode,
} from './search-utils';

const ENTITY_ICONS: Record<string, React.ReactNode> = {
  drug: <Pill size={14} />,
  trial: <FlaskConical size={14} />,
  literature: <BookOpen size={14} />,
  company: <Building2 size={14} />,
  therapeutic_area: <Target size={14} />,
};

const FILTER_COLORS: Record<string, { color: string; bg: string }> = {
  drug:             { color: 'var(--color-drug)',       bg: 'rgba(37, 99, 235, 0.08)' },
  trial:            { color: 'var(--color-trial)',      bg: 'rgba(13, 148, 136, 0.08)' },
  literature:       { color: 'var(--color-literature)', bg: 'rgba(5, 150, 105, 0.08)' },
  company:          { color: 'var(--color-company)',    bg: 'rgba(217, 119, 6, 0.08)' },
  therapeutic_area: { color: 'var(--color-ta)',         bg: 'rgba(225, 29, 72, 0.08)' },
};

interface SearchFiltersProps {
  activeTypes: string[];
  onTypeToggle: (type: string) => void;
  sortMode: SortMode;
  onSortChange: (mode: SortMode) => void;
  viewMode: SearchViewMode;
  onViewChange: (mode: SearchViewMode) => void;
  therapeuticAreaOptions: string[];
  selectedTherapeuticAreas: string[];
  onTherapeuticAreaToggle: (ta: string) => void;
  onClearTherapeuticAreas: () => void;
}

export default function SearchFilters({
  activeTypes,
  onTypeToggle,
  sortMode,
  onSortChange,
  viewMode,
  onViewChange,
  therapeuticAreaOptions,
  selectedTherapeuticAreas,
  onTherapeuticAreaToggle,
  onClearTherapeuticAreas,
}: SearchFiltersProps) {
  return (
    <div>
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        {ENTITY_TYPES.map((entityType) => {
          const active = activeTypes.includes(entityType.key);
          const cfg = FILTER_COLORS[entityType.key];
          return (
            <button
              key={entityType.key}
              type="button"
              onClick={() => onTypeToggle(entityType.key)}
              className="flex items-center gap-1.5 rounded-full px-4 py-2 text-[12px] font-medium transition-all"
              style={{
                background: active ? cfg.bg : 'var(--color-surface-2)',
                color: active ? cfg.color : 'var(--color-ink-3)',
              }}
            >
              {ENTITY_ICONS[entityType.key]}
              {entityType.label}
            </button>
          );
        })}
        {activeTypes.length > 0 && (
          <button
            type="button"
            onClick={() => {
              for (const type of [...activeTypes]) {
                onTypeToggle(type);
              }
            }}
            className="rounded-full px-4 py-2 text-[12px] font-medium transition-colors"
            style={{
              background: 'var(--color-surface-2)',
              color: 'var(--color-ink-4)',
            }}
          >
            Clear
          </button>
        )}
      </div>

      {activeTypes.includes('therapeutic_area') && (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
          <span
            className="rounded-md px-3 py-1.5 text-[11px] font-medium"
            style={{
              border: '1px solid rgba(225, 29, 72, 0.25)',
              background: 'rgba(225, 29, 72, 0.08)',
              color: 'var(--color-ta)',
            }}
          >
            Select TA
          </span>
          {therapeuticAreaOptions.length === 0 && (
            <span className="text-[11px]" style={{ color: 'var(--color-ink-3)' }}>
              No therapeutic-area tags available for this query yet.
            </span>
          )}
          {therapeuticAreaOptions.slice(0, 12).map((ta) => {
            const active = selectedTherapeuticAreas.includes(ta);
            return (
              <button
                key={ta}
                type="button"
                onClick={() => onTherapeuticAreaToggle(ta)}
                className="rounded-md px-3 py-1.5 text-[11px] font-medium transition-colors"
                style={{
                  border: active
                    ? '1px solid rgba(225, 29, 72, 0.25)'
                    : '1px solid var(--color-line)',
                  background: active ? 'rgba(225, 29, 72, 0.12)' : 'transparent',
                  color: active ? 'var(--color-ta)' : 'var(--color-ink-2)',
                }}
              >
                {ta}
              </button>
            );
          })}
          {selectedTherapeuticAreas.length > 0 && (
            <button
              type="button"
              onClick={onClearTherapeuticAreas}
              className="rounded-md px-3 py-1.5 text-[11px] font-medium transition-colors"
              style={{
                border: '1px solid var(--color-line)',
                color: 'var(--color-ink-3)',
              }}
            >
              Clear TA
            </button>
          )}
        </div>
      )}
    </div>
  );
}

interface ResultsToolbarProps {
  resultTypeCounts: Map<string, number>;
  highConfidenceCount: number;
  viewMode: SearchViewMode;
  onViewChange: (mode: SearchViewMode) => void;
  sortMode: SortMode;
  onSortChange: (mode: SortMode) => void;
}

export function ResultsToolbar({
  resultTypeCounts,
  highConfidenceCount,
  viewMode,
  onViewChange,
  sortMode,
  onSortChange,
}: ResultsToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {Array.from(resultTypeCounts.entries()).map(([type, count]) => (
          <span
            key={type}
            className="chip-plain text-[11px]"
            style={{ color: 'var(--color-ink-3)' }}
          >
            {type.replace(/_/g, ' ').toLowerCase()}:{' '}
            <span className="font-semibold" style={{ color: 'var(--color-ink)' }}>
              {count}
            </span>
          </span>
        ))}
        <span
          className="rounded-md px-3 py-1.5 text-[11px]"
          style={{
            border: '1px solid rgba(26, 127, 75, 0.25)',
            background: 'var(--color-green-soft)',
            color: 'var(--color-green)',
          }}
        >
          {highConfidenceCount} high-confidence
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div
          className="inline-flex items-center rounded-md p-1"
          style={{
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
          }}
        >
          {VIEW_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onViewChange(option.value)}
              className="rounded-md px-3 py-1.5 text-xs transition-colors"
              style={{
                background: viewMode === option.value ? 'var(--color-accent-soft)' : 'transparent',
                fontWeight: viewMode === option.value ? 600 : 400,
                color: viewMode === option.value ? 'var(--color-ink)' : 'var(--color-ink-3)',
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <select
          value={sortMode}
          onChange={(e) => onSortChange(e.target.value as SortMode)}
          className="rounded-md px-3.5 py-1.5 text-xs outline-none"
          aria-label="Sort results"
          style={{
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            color: 'var(--color-ink-2)',
          }}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
