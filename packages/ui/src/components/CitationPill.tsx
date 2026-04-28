import type { MouseEvent } from 'react';

export type SourceClass =
  | 'edgar' | 'fda' | 'ema' | 'ct_gov' | 'pubmed' | 'pmc' | 'dailymed'
  | 'orange_book' | 'patent' | 'press' | 'news' | 'tier3' | 'signal' | 'unknown';

const SOURCE_LABEL: Record<SourceClass, string> = {
  edgar: 'EDGAR', fda: 'FDA', ema: 'EMA', ct_gov: 'CT.gov', pubmed: 'PubMed',
  pmc: 'PMC', dailymed: 'DailyMed', orange_book: 'OrangeBook', patent: 'PATENT',
  press: 'PRESS', news: 'NEWS', tier3: 'TIER3', signal: 'SIGNAL', unknown: 'SRC',
};

export interface CitationPillProps {
  /** The source class — drives color + label. */
  source: SourceClass;
  /** Index or short identifier (e.g. "0", "abc123"). */
  ref: string | number;
  /** Optional click handler — typically jumps to the cited document. */
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  /** Tooltip text (e.g. the document title). */
  title?: string;
}

/**
 * CitationPill — inline citation marker. Renders as `[edgar:0]` style.
 * Source-color-coded; click jumps to the originating document or signal.
 *
 * Used inside synthesis paragraphs and brief drafts.
 */
export function CitationPill({ source, ref, onClick, title }: CitationPillProps) {
  const label = SOURCE_LABEL[source];
  const isSignalRef = source === 'signal';

  return (
    <button
      type="button"
      onClick={onClick}
      title={title ?? `Source: ${label}`}
      aria-label={`Citation ${label} ${ref}`}
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        gap: 2,
        padding: '0 6px',
        margin: '0 2px',
        borderRadius: 'var(--mz-radius-pill)',
        background: isSignalRef
          ? `color-mix(in oklab, var(--mz-color-accent) 18%, transparent)`
          : `color-mix(in oklab, var(--mz-color-text-secondary) 14%, transparent)`,
        color: isSignalRef ? 'var(--mz-color-accent)' : 'var(--mz-color-text-secondary)',
        border: `1px solid color-mix(in oklab, ${isSignalRef ? 'var(--mz-color-accent)' : 'var(--mz-color-text-secondary)'} 24%, transparent)`,
        fontFamily: 'var(--mz-font-mono)',
        fontSize: 'var(--mz-text-mono-3)',
        fontWeight: 'var(--mz-weight-medium)' as never,
        letterSpacing: 'var(--mz-tracking-wide)',
        cursor: onClick ? 'pointer' : 'default',
        verticalAlign: 'baseline',
        textTransform: 'uppercase',
        transition: 'background var(--mz-duration-fast) var(--mz-ease-standard)',
      }}
    >
      <span>{label}</span>
      <span aria-hidden style={{ opacity: 0.6 }}>:</span>
      <span>{ref}</span>
    </button>
  );
}
