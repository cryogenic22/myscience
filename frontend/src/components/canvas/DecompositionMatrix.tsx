import { ExternalLink } from 'lucide-react';
import type { CoverageState, DecompositionMatrix as MatrixData, MatrixCell, MatrixFact } from '../../api';
import FactClassGlyph from '../ci/FactClassGlyph';
import type { FactClass } from '../../lib/helix';

/**
 * DI-3 — decomposition matrix renderer (rows = dimensions, columns = entities).
 *
 * Each cell shows the grounded claim(s) for that dimension × entity with a
 * fact-class glyph + source link. Cells with no facts render as an explicit,
 * muted "gap — no facts in KB" affordance — never hidden — so the absence of
 * evidence is legible rather than silently dropped (DI-3 honesty contract).
 *
 * Styling follows the house pattern: design-token CSS variables + inline
 * styles, no dynamic Tailwind class names (Tailwind v4 / Railway scanner).
 */

const COVERAGE_META: Record<CoverageState, { label: string; color: string; soft: string }> = {
  covered: { label: 'covered', color: 'var(--color-green)', soft: 'var(--color-green-soft)' },
  thin: { label: 'thin', color: 'var(--color-amber)', soft: 'var(--color-amber-soft)' },
  gap: { label: 'gap', color: 'var(--color-ink-4)', soft: 'var(--color-surface-3)' },
};

export default function DecompositionMatrix({ matrix }: { matrix: MatrixData }) {
  const { entities, dimensions } = matrix;
  if (!dimensions.length || !entities.length) return null;

  // Index cells by "dimension|entity" for O(1) lookup while rendering the grid.
  const cellMap = new Map<string, MatrixCell>();
  for (const c of matrix.cells) cellMap.set(`${c.dimension}|${c.entity_id}`, c);

  // Fixed-width dimension column + equal-share entity columns.
  const gridTemplate = `minmax(120px, 0.8fr) repeat(${entities.length}, minmax(180px, 1fr))`;

  return (
    <div data-testid="decomposition-matrix" style={{ overflowX: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: gridTemplate, minWidth: 'min-content' }}>
        {/* Header row: blank corner + entity columns */}
        <HeaderCorner />
        {entities.map((e) => (
          <div
            key={e.entity_id}
            data-testid={`matrix-col-${e.entity_id}`}
            style={{
              padding: '10px 12px',
              borderBottom: '1px solid var(--color-line)',
              borderLeft: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--color-ink)',
              position: 'sticky',
              top: 0,
              zIndex: 1,
            }}
          >
            {e.label}
            {e.entity_type && (
              <span style={{ display: 'block', fontSize: '10px', fontWeight: 500, color: 'var(--color-ink-4)', textTransform: 'capitalize', marginTop: '1px' }}>
                {e.entity_type.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        ))}

        {/* Body: one row per dimension */}
        {dimensions.map((d) => (
          <DimensionRow
            key={d.key}
            label={d.label}
            subQuestion={d.sub_question}
            rollup={matrix.coverage_summary[d.key]}
            cells={entities.map((e) => cellMap.get(`${d.key}|${e.entity_id}`))}
            entities={entities}
          />
        ))}
      </div>
    </div>
  );
}

function HeaderCorner() {
  return (
    <div
      style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
        fontSize: '10px',
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-4)',
        position: 'sticky',
        top: 0,
        left: 0,
        zIndex: 2,
      }}
    >
      Dimension
    </div>
  );
}

function DimensionRow({
  label,
  subQuestion,
  rollup,
  cells,
  entities,
}: {
  label: string;
  subQuestion: string;
  rollup?: CoverageState;
  cells: Array<MatrixCell | undefined>;
  entities: MatrixData['entities'];
}) {
  return (
    <>
      {/* Row header — the dimension */}
      <div
        style={{
          padding: '12px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface-2)',
          position: 'sticky',
          left: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink)' }}>{label}</span>
          {rollup && <CoverageBadge state={rollup} />}
        </div>
        {subQuestion && (
          <div style={{ fontSize: '10.5px', color: 'var(--color-ink-4)', marginTop: '3px', lineHeight: 1.4 }}>
            {subQuestion}
          </div>
        )}
      </div>

      {/* One cell per entity */}
      {entities.map((e, i) => (
        <MatrixCellView key={e.entity_id} dimensionKey={cells[i]?.dimension ?? ''} entityId={e.entity_id} cell={cells[i]} />
      ))}
    </>
  );
}

function CoverageBadge({ state }: { state: CoverageState }) {
  const meta = COVERAGE_META[state];
  return (
    <span
      style={{
        fontSize: '9px',
        fontWeight: 600,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        padding: '1px 6px',
        borderRadius: '999px',
        background: meta.soft,
        color: meta.color,
      }}
    >
      {meta.label}
    </span>
  );
}

function MatrixCellView({
  dimensionKey,
  entityId,
  cell,
}: {
  dimensionKey: string;
  entityId: string;
  cell: MatrixCell | undefined;
}) {
  const coverage: CoverageState = cell?.coverage ?? 'gap';
  // The data-testid uses the cell's own dimension when present (the row header
  // doesn't know the dimension key for a missing cell — fall back to a stable id).
  const testId = `matrix-cell-${cell?.dimension ?? dimensionKey}-${entityId}`;

  return (
    <div
      data-testid={testId}
      style={{
        padding: '12px',
        borderBottom: '1px solid var(--color-line)',
        borderLeft: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: '6px' }}>
        <CoverageBadge state={coverage} />
      </div>

      {cell && cell.facts.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {cell.facts.map((f) => (
            <CellFact key={f.id || f.claim} fact={f} />
          ))}
        </div>
      ) : (
        <GapState />
      )}
    </div>
  );
}

function CellFact({ fact }: { fact: MatrixFact }) {
  return (
    <div style={{ fontSize: '12px', lineHeight: 1.5, color: 'var(--color-ink-2)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
        <span style={{ marginTop: '1px', flexShrink: 0 }}>
          <FactClassGlyph factClass={fact.fact_class as FactClass} size={14} />
        </span>
        <span>{fact.claim}</span>
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          marginTop: '3px',
          paddingLeft: '20px',
          fontSize: '10px',
          color: 'var(--color-ink-4)',
        }}
      >
        <span>{fact.source_label}</span>
        {fact.source_url && (
          <a
            href={fact.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '2px', color: 'var(--color-accent)', textDecoration: 'none' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none'; }}
          >
            <ExternalLink size={9} />
            source
          </a>
        )}
      </div>
    </div>
  );
}

function GapState() {
  return (
    <div
      style={{
        fontSize: '11px',
        fontStyle: 'italic',
        color: 'var(--color-ink-4)',
        lineHeight: 1.4,
      }}
    >
      gap — no facts in KB
    </div>
  );
}
