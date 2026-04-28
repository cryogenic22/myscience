/**
 * @mz/ui — shared component primitives.
 *
 * Phase 0 / M0 set:
 *   - Card           (the universal composition primitive)
 *   - Pill           (small status / tier label)
 *   - KbqTag         (KBQ membership marker, built on Pill)
 *   - CitationPill   (inline source citation)
 *   - ScoreTile      (one big number + label, "Apple Health" tile)
 *
 * Phase 1 will add: SignalCard, EvidenceStack, ConflictBadge, EntityChip,
 * TimeRangeSelector, CommandPalette, KeyboardHint, DataTable, Sheet,
 * EmptyState, FreshnessIndicator.
 */

export { Card } from './components/Card';
export type { CardProps, CardVariant } from './components/Card';

export { Pill } from './components/Pill';
export type { PillProps, PillTone, PillSize } from './components/Pill';

export { KbqTag } from './components/KbqTag';
export type { KbqTagProps, Kbq } from './components/KbqTag';

export { CitationPill } from './components/CitationPill';
export type { CitationPillProps, SourceClass } from './components/CitationPill';

export { ScoreTile } from './components/ScoreTile';
export type { ScoreTileProps, ScoreTileTrend } from './components/ScoreTile';
