import {
  Search,
  Pill,
  Building2,
  FlaskConical,
  BookOpen,
  Dna,
  Target,
  ShieldCheck,
  Clock3,
  ChevronRight,
} from 'lucide-react';
import type { SearchResult } from '../../api';
import {
  TYPE_CONFIG,
  type SearchViewMode,
  prettyType,
  truncateValue,
  formatDate,
  getResultSnippet,
  getSourcePublicationDate,
  resultFingerprint,
  safeTileValue,
} from './search-utils';

const ENTITY_ICONS_LARGE: Record<string, React.ReactNode> = {
  drug: <Pill size={20} />,
  trial: <FlaskConical size={20} />,
  literature: <BookOpen size={20} />,
  company: <Building2 size={20} />,
  mechanism: <Dna size={20} />,
  therapeutic_area: <Target size={20} />,
};

const ENTITY_ICONS_SMALL: Record<string, React.ReactNode> = {
  drug: <Pill size={16} />,
  trial: <FlaskConical size={16} />,
  literature: <BookOpen size={16} />,
  company: <Building2 size={16} />,
  mechanism: <Dna size={16} />,
  therapeutic_area: <Target size={16} />,
};

interface SearchResultsProps {
  results: SearchResult[];
  viewMode: SearchViewMode;
  activeResultKey: string | null;
  onEntityClick: (result: SearchResult) => void;
  isLoading: boolean;
  hasSearched: boolean;
  query: string;
  totalResults: number;
  visibleCount: number;
}

export default function SearchResults({
  results,
  viewMode,
  activeResultKey,
  onEntityClick,
  isLoading,
  hasSearched,
  query,
  totalResults,
  visibleCount,
}: SearchResultsProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div
          className="w-6 h-6 rounded-full animate-spin"
          style={{
            border: '2px solid var(--color-accent)',
            borderTopColor: 'transparent',
          }}
        />
        <span className="ml-3 text-sm" style={{ color: 'var(--color-ink-3)' }}>
          Searching knowledge graph...
        </span>
      </div>
    );
  }

  if (hasSearched && totalResults === 0) {
    return (
      <div className="text-center py-20">
        <div
          className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-md"
          style={{
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
          }}
        >
          <Search size={28} style={{ color: 'var(--color-ink-4)' }} />
        </div>
        <p className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
          No results found for "{query}"
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--color-ink-4)' }}>
          Try broader keywords or remove filters.
        </p>
      </div>
    );
  }

  if (hasSearched && totalResults > 0 && visibleCount === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
          No results match the selected therapeutic areas.
        </p>
        <p className="mt-1 text-xs" style={{ color: 'var(--color-ink-3)' }}>
          Try different TA chips or clear the TA filter.
        </p>
      </div>
    );
  }

  if (!hasSearched || results.length === 0) {
    return null;
  }

  const containerClass =
    viewMode === 'grid'
      ? 'grid grid-cols-1 gap-3 md:grid-cols-2'
      : viewMode === 'list'
        ? 'overflow-hidden rounded-md divide-y'
        : 'space-y-3';

  const containerStyle =
    viewMode === 'list'
      ? {
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }
      : undefined;

  return (
    <div className={containerClass} style={containerStyle}>
      {results.map((result, index) => (
        <SearchResultCard
          key={`${resultFingerprint(result)}-${index}`}
          result={result}
          active={activeResultKey === resultFingerprint(result)}
          onSelect={() => onEntityClick(result)}
          mode={viewMode}
        />
      ))}
    </div>
  );
}

function SearchResultCard({
  result,
  active,
  onSelect,
  mode,
}: {
  result: SearchResult;
  active: boolean;
  onSelect: () => void;
  mode: SearchViewMode;
}) {
  const cfg = TYPE_CONFIG[result.entity_type] ?? {
    color: 'var(--color-ink-3)',
    bgVar: 'rgba(148, 163, 184, 0.08)',
    label: result.entity_type,
  };
  const icon = ENTITY_ICONS_LARGE[result.entity_type] ?? <Search size={20} />;
  const smallIcon = ENTITY_ICONS_SMALL[result.entity_type] ?? <Search size={16} />;

  const sourceApi = String(result.provenance?.source_api ?? 'unknown source');
  const retrievedAt = result.provenance?.retrieved_at ? String(result.provenance.retrieved_at) : null;
  const sourcePublishedAt = getSourcePublicationDate(result.metadata);
  const previewSnippet = getResultSnippet(result);
  const similarity = (result.similarity * 100).toFixed(0);
  const quality = typeof result.quality_score === 'number' ? (result.quality_score * 100).toFixed(0) : null;
  const metadata = Object.entries(result.metadata ?? {})
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
    .slice(0, mode === 'cards' ? 4 : 2);
  const compact = mode === 'list';

  if (compact) {
    return (
      <button
        type="button"
        onClick={onSelect}
        className="group relative w-full text-left transition-colors"
        style={{
          background: active ? 'var(--color-accent-soft)' : 'transparent',
          borderColor: 'var(--color-line)',
        }}
      >
        <span
          className="absolute inset-y-0 left-0 w-[2px] transition-opacity"
          style={{
            background: 'var(--color-accent)',
            opacity: active ? 1 : 0,
          }}
          aria-hidden
        />
        <div className="flex items-start gap-3 px-4 py-3.5">
          <div
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm"
            style={{ background: cfg.bgVar, color: cfg.color }}
          >
            {smallIcon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3
                  className="truncate text-[14px] font-semibold"
                  style={{ color: 'var(--color-ink)' }}
                >
                  {result.title}
                </h3>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <span
                    className="inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
                    style={{ background: cfg.bgVar, color: cfg.color }}
                  >
                    {cfg.label}
                  </span>
                  <span
                    className="chip-plain max-w-[12rem] truncate text-[11px]"
                    style={{ color: 'var(--color-ink-3)' }}
                  >
                    {sourceApi}
                  </span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-[12px] font-semibold" style={{ color: 'var(--color-ink)' }}>
                  {similarity}%
                </div>
                <div
                  className="text-[10px] uppercase tracking-wide"
                  style={{ color: 'var(--color-ink-3)' }}
                >
                  match
                </div>
              </div>
            </div>

            {previewSnippet && (
              <p
                className="mt-2 line-clamp-2 text-[12px] leading-relaxed"
                style={{ color: 'var(--color-ink-2)' }}
              >
                {previewSnippet}
              </p>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
              {quality && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-2.5 py-0.5"
                  style={{
                    border: '1px solid rgba(26, 127, 75, 0.25)',
                    background: 'var(--color-green-soft)',
                    color: 'var(--color-green)',
                  }}
                >
                  quality {quality}%
                </span>
              )}
              {sourcePublishedAt && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-2.5 py-0.5"
                  style={{
                    border: '1px solid var(--color-line)',
                    background: 'var(--color-surface)',
                    color: 'var(--color-ink-3)',
                  }}
                >
                  <Clock3 size={11} />
                  Source {formatDate(sourcePublishedAt)}
                </span>
              )}
              {retrievedAt && (
                <span
                  className="inline-flex items-center gap-1 rounded-sm px-2.5 py-0.5"
                  style={{
                    border: '1px solid var(--color-line)',
                    background: 'var(--color-surface)',
                    color: 'var(--color-ink-3)',
                  }}
                >
                  <Clock3 size={11} />
                  Ingested {formatDate(retrievedAt)}
                </span>
              )}
            </div>
          </div>
          <ChevronRight
            size={16}
            className={`shrink-0 transition-transform ${active ? 'translate-x-0.5' : 'group-hover:translate-x-0.5'}`}
            style={{ color: 'var(--color-ink-4)' }}
          />
        </div>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group w-full text-left transition-all ${mode === 'grid' ? 'min-h-[206px]' : ''}`}
      style={{
        border: active ? '1px solid var(--color-accent)' : '1px solid var(--color-line)',
        background: active ? 'var(--color-surface)' : 'var(--color-surface)',
        boxShadow: active ? 'var(--shadow-sm)' : 'none',
      }}
    >
      <div className="flex items-start gap-4 p-5">
        <div
          className={`flex shrink-0 items-center justify-center rounded-sm ${mode === 'grid' ? 'h-10 w-10' : 'h-11 w-11'}`}
          style={{ background: cfg.bgVar, color: cfg.color }}
        >
          {mode === 'grid' ? smallIcon : icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2.5">
            <h3
              className="truncate text-[15px] font-semibold"
              style={{ color: 'var(--color-ink)' }}
            >
              {result.title}
            </h3>
            <span
              className="shrink-0 inline-flex items-center gap-1 rounded-sm px-3 py-1 text-[10px] font-medium uppercase tracking-wide"
              style={{ background: cfg.bgVar, color: cfg.color }}
            >
              {cfg.label}
            </span>
          </div>

          {previewSnippet && (
            <p
              className={`leading-relaxed ${mode === 'grid' ? 'line-clamp-2 text-[12px]' : 'line-clamp-4 text-[13px]'}`}
              style={{ color: 'var(--color-ink-2)' }}
            >
              {previewSnippet}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
            <span
              className="inline-flex items-center gap-1 rounded-sm px-3 py-1"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink-3)',
              }}
            >
              <ShieldCheck size={11} />
              {similarity}% match
            </span>
            {quality && (
              <span
                className="inline-flex items-center gap-1 rounded-sm px-3 py-1"
                style={{
                  border: '1px solid rgba(26, 127, 75, 0.25)',
                  background: 'var(--color-green-soft)',
                  color: 'var(--color-green)',
                }}
              >
                quality {quality}%
              </span>
            )}
            <span
              className="chip-plain inline-flex max-w-[12rem] items-center gap-1 truncate px-1 py-1"
              style={{ color: 'var(--color-ink-3)' }}
            >
              {sourceApi}
            </span>
            {sourcePublishedAt && (
              <span
                className="inline-flex items-center gap-1 rounded-sm px-3 py-1"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink-3)',
                }}
              >
                <Clock3 size={11} />
                Source {formatDate(sourcePublishedAt)}
              </span>
            )}
            {retrievedAt && (
              <span
                className="inline-flex items-center gap-1 rounded-sm px-3 py-1"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink-3)',
                }}
              >
                <Clock3 size={11} />
                Ingested {formatDate(retrievedAt)}
              </span>
            )}
          </div>

          {mode === 'cards' && metadata.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              {metadata.map(([key, value]) => (
                <span
                  key={key}
                  className="inline-flex items-center text-xs"
                  style={{ color: 'var(--color-ink-3)' }}
                >
                  <span className="font-medium capitalize" style={{ color: 'var(--color-ink-2)' }}>
                    {prettyType(key)}:
                  </span>
                  <span className="ml-1">{truncateValue(value, 34)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 pt-1">
          <ChevronRight
            size={16}
            className={`transition-transform ${active ? 'translate-x-0.5' : 'group-hover:translate-x-0.5'}`}
            style={{ color: 'var(--color-ink-4)' }}
          />
        </div>
      </div>
    </button>
  );
}

interface InsightTileProps {
  label: string;
  value: string;
}

export function InsightTile({ label, value }: InsightTileProps) {
  return (
    <div
      className="rounded-md px-3.5 py-3"
      style={{
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}
    >
      <div
        className="text-[10px] font-medium uppercase tracking-wide"
        style={{ color: 'var(--color-ink-4)' }}
      >
        {label}
      </div>
      <div
        className="mt-1 truncate text-[13px] font-semibold"
        style={{ color: 'var(--color-ink)' }}
      >
        {value}
      </div>
    </div>
  );
}
