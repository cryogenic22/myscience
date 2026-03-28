import {
  Search,
  Pill,
  Building2,
  FlaskConical,
  BookOpen,
  Dna,
  Target,
  ChevronRight,
} from 'lucide-react';
import type { SearchResult } from '../../api';
import { SOURCE_LABELS, ENTITY_TYPE_LABELS } from '../../brand';
import {
  TYPE_CONFIG,
  type SearchViewMode,
  prettyType,
  truncateValue,
  getResultSnippet,
  getSourcePublicationDate,
  resultFingerprint,
} from './search-utils';

/* ── Relative time helper ── */

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (Number.isNaN(then)) return dateStr;
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  return `${Math.floor(diffMonths / 12)}y ago`;
}

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

/* ── Connection count bar ── */

function ConnectionBar({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, v]) => v > 0);
  if (entries.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
      {entries.map(([type, count]) => {
        const cfg = TYPE_CONFIG[type];
        const color = cfg?.color ?? 'var(--color-ink-3)';
        const label = ENTITY_TYPE_LABELS[type] ?? type.replace(/_/g, ' ');
        return (
          <span
            key={type}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontWeight: 500,
              color: 'var(--color-ink-3)',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: color,
                flexShrink: 0,
              }}
            />
            {count} {label.toLowerCase()}{count !== 1 ? 's' : ''}
          </span>
        );
      })}
    </div>
  );
}

/* ── Influence indicator (5 dots) ── */

function InfluenceIndicator({ score }: { score: number }) {
  const filled = Math.round(Math.min(Math.max(score, 0), 1) * 5);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '11px',
        fontWeight: 500,
        color: 'var(--color-ink-3)',
      }}
    >
      Influence:
      <span style={{ display: 'inline-flex', gap: '2px' }}>
        {Array.from({ length: 5 }, (_, i) => (
          <span
            key={i}
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: i < filled ? 'var(--color-accent)' : 'var(--color-line)',
            }}
          />
        ))}
      </span>
    </span>
  );
}

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
      <div className="flex items-center justify-center" style={{ padding: '80px 0' }}>
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
      <div className="text-center" style={{ padding: '80px 0' }}>
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
      <div className="text-center" style={{ padding: '64px 0' }}>
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

  const sourceApi = String(result.provenance?.source_api ?? 'unknown');
  const sourceLabel = SOURCE_LABELS[sourceApi] ?? sourceApi.replace(/_/g, ' ');
  const retrievedAt = result.provenance?.retrieved_at ? String(result.provenance.retrieved_at) : null;
  const sourcePublishedAt = getSourcePublicationDate(result.metadata);
  const previewSnippet = getResultSnippet(result);
  const quality = typeof result.quality_score === 'number' ? (result.quality_score * 100).toFixed(0) : null;
  const metadata = Object.entries(result.metadata ?? {})
    .filter(([key, value]) =>
      value !== null &&
      value !== undefined &&
      String(value).trim() !== '' &&
      key !== 'content_hash' &&
      !key.endsWith('_embedding')
    )
    .slice(0, mode === 'cards' ? 4 : 2);

  // Enriched search fields (graceful degradation — only render when present)
  const connectionCounts = (result as Record<string, unknown>).connection_counts as Record<string, number> | undefined;
  const influenceScore = (result as Record<string, unknown>).influence_score as number | undefined;

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
        <div className="flex items-start gap-3" style={{ padding: '14px 24px' }}>
          {/* Entity type color dot */}
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: cfg.color,
              flexShrink: 0,
              marginTop: '6px',
            }}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3
                  className="truncate text-[14px] font-semibold"
                  style={{ color: 'var(--color-ink)' }}
                >
                  {result.title}
                </h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      fontSize: '10px',
                      fontWeight: 600,
                      textTransform: 'uppercase' as const,
                      letterSpacing: '0.04em',
                      padding: '2px 8px',
                      borderRadius: '10px',
                      background: cfg.bgVar,
                      color: cfg.color,
                    }}
                  >
                    {cfg.label}
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--color-ink-4)',
                    maxWidth: '160px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap' as const,
                  }}>
                    {sourceLabel}
                  </span>
                  {typeof influenceScore === 'number' && (
                    <InfluenceIndicator score={influenceScore} />
                  )}
                </div>
              </div>
            </div>

            {connectionCounts && <ConnectionBar counts={connectionCounts} />}

            {previewSnippet && (
              <p
                className="mt-2 line-clamp-2 text-[12px] leading-relaxed"
                style={{ color: 'var(--color-ink-2)' }}
              >
                {previewSnippet}
              </p>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginTop: '8px', fontSize: '11px' }}>
              {quality && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 10px',
                    borderRadius: '10px',
                    border: '1px solid rgba(26, 127, 75, 0.25)',
                    background: 'var(--color-green-soft)',
                    color: 'var(--color-green)',
                  }}
                >
                  {quality}% quality
                </span>
              )}
              {sourcePublishedAt && (
                <span style={{ color: 'var(--color-ink-4)' }}>
                  {new Date(sourcePublishedAt).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })}
                </span>
              )}
              {retrievedAt && (
                <span style={{ color: 'var(--color-ink-4)' }}>
                  {relativeTime(retrievedAt)}
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
        background: 'var(--color-surface)',
        boxShadow: active ? 'var(--shadow-sm)' : 'none',
        borderRadius: '8px',
      }}
    >
      <div className="flex items-start gap-4" style={{ padding: '20px 24px' }}>
        <div
          className={`flex shrink-0 items-center justify-center rounded-sm ${mode === 'grid' ? 'h-10 w-10' : 'h-11 w-11'}`}
          style={{ background: cfg.bgVar, color: cfg.color }}
        >
          {mode === 'grid' ? smallIcon : icon}
        </div>
        <div className="min-w-0 flex-1">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            {/* Entity type color dot */}
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: cfg.color,
                flexShrink: 0,
              }}
            />
            <h3
              className="truncate text-[15px] font-semibold"
              style={{ color: 'var(--color-ink)', flex: 1, minWidth: 0 }}
            >
              {result.title}
            </h3>
            <span
              className="shrink-0 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide"
              style={{ padding: '4px 12px', borderRadius: '12px', background: cfg.bgVar, color: cfg.color }}
            >
              {cfg.label}
            </span>
          </div>

          {/* Enriched search: connection counts + influence */}
          {(connectionCounts || typeof influenceScore === 'number') && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
              {connectionCounts && <ConnectionBar counts={connectionCounts} />}
              {typeof influenceScore === 'number' && <InfluenceIndicator score={influenceScore} />}
            </div>
          )}

          {previewSnippet && (
            <p
              className={`leading-relaxed ${mode === 'grid' ? 'line-clamp-2 text-[12px]' : 'line-clamp-4 text-[13px]'}`}
              style={{ color: 'var(--color-ink-2)' }}
            >
              {previewSnippet}
            </p>
          )}

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginTop: '10px', fontSize: '11px' }}>
            {/* Source badge */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '3px 10px',
                borderRadius: '10px',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-3)',
                fontWeight: 500,
              }}
            >
              {sourceLabel}
            </span>
            {quality && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '3px 10px',
                  borderRadius: '10px',
                  border: '1px solid rgba(26, 127, 75, 0.25)',
                  background: 'var(--color-green-soft)',
                  color: 'var(--color-green)',
                }}
              >
                {quality}% quality
              </span>
            )}
            {sourcePublishedAt && (
              <span style={{ color: 'var(--color-ink-4)' }}>
                {new Date(sourcePublishedAt).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })}
              </span>
            )}
            {retrievedAt && (
              <span style={{ color: 'var(--color-ink-4)' }}>
                {relativeTime(retrievedAt)}
              </span>
            )}
          </div>

          {mode === 'cards' && metadata.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px 16px', marginTop: '8px' }}>
              {metadata.map(([key, value]) => (
                <span
                  key={key}
                  style={{ display: 'inline-flex', alignItems: 'center', fontSize: '12px', color: 'var(--color-ink-3)' }}
                >
                  <span style={{ fontWeight: 500, color: 'var(--color-ink-2)', textTransform: 'capitalize' as const }}>
                    {prettyType(key)}:
                  </span>
                  <span style={{ marginLeft: '4px' }}>{truncateValue(value, 34)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0" style={{ paddingTop: '4px' }}>
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
      className="rounded-md"
      style={{
        padding: '14px 16px',
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}
    >
      <div
        style={{
          fontSize: '10px',
          fontWeight: 500,
          textTransform: 'uppercase' as const,
          letterSpacing: '0.06em',
          color: 'var(--color-ink-4)',
        }}
      >
        {label}
      </div>
      <div
        style={{
          marginTop: '4px',
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--color-ink)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
        }}
      >
        {value}
      </div>
    </div>
  );
}
