/**
 * Loop #20 — Materiality Drawer.
 *
 * Opens from the right edge when a user clicks a materiality score on
 * any signal. Shows the four factor contributions (source_tier,
 * entity_criticality, claim_type, recency) with their input values,
 * weight, and contribution to the composite score.
 *
 * Closes on Escape, click of the close button, or click outside the
 * panel. The formula is shown so the score is always defensible.
 */
import { useEffect } from 'react';
import type {
  MaterialityFactor,
  MaterialityFactors,
} from '../../types/materiality';

const FACTOR_ORDER: Array<keyof MaterialityFactors> = [
  'source_tier',
  'entity_criticality',
  'claim_type',
  'recency',
];

const FACTOR_LABELS: Record<keyof MaterialityFactors, string> = {
  source_tier: 'Source Tier',
  entity_criticality: 'Entity Criticality',
  claim_type: 'Claim Type',
  recency: 'Recency',
};

const FACTOR_HINTS: Record<keyof MaterialityFactors, string> = {
  source_tier:
    'How authoritative the originating source is. Tier 1 = clinical registries + peer-reviewed; Tier 2 = regulatory + reference DBs; Tier 3 = news.',
  entity_criticality:
    'How central this entity is to your watchlist or strategic context.',
  claim_type:
    'The kind of claim — trial readouts and regulatory actions count more than routine updates.',
  recency: 'Half-life decay. Fresher signals contribute more.',
};

function formatInput(
  factor: keyof MaterialityFactors,
  v: MaterialityFactor['input'],
): string {
  if (v === null || v === undefined) return '—';
  if (factor === 'source_tier') {
    if (typeof v === 'number') return `Tier ${v}`;
    return String(v);
  }
  if (factor === 'recency') {
    if (typeof v === 'number') {
      return `${v.toFixed(1)} days old`;
    }
    return String(v);
  }
  return String(v);
}

function FactorRow({
  factor,
  data,
}: {
  factor: keyof MaterialityFactors;
  data: MaterialityFactor;
}) {
  // Bar width = contribution as % (max 100). Color: ink at full opacity.
  const widthPct = Math.max(0, Math.min(100, data.contribution));
  return (
    <div
      style={{
        padding: '14px 0',
        borderBottom: '1px solid var(--color-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2 min-w-0">
          <span
            className="text-[12px] font-medium"
            style={{ color: 'var(--color-ink)' }}
          >
            {FACTOR_LABELS[factor]}
          </span>
          <span
            className="text-[11px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            · {formatInput(factor, data.input)}
          </span>
        </div>
        <span
          className="text-[12px] font-medium tabular-nums"
          style={{ color: 'var(--color-ink)' }}
        >
          {data.contribution.toFixed(1)}%
        </span>
      </div>
      <div
        style={{
          height: '6px',
          width: '100%',
          background: 'var(--color-surface-2)',
          borderRadius: '999px',
          overflow: 'hidden',
        }}
      >
        <div
          data-factor-bar={factor}
          style={{
            width: `${widthPct}%`,
            height: '100%',
            background: 'var(--color-ink)',
            transition: 'width 220ms ease',
          }}
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <span
          className="text-[10px]"
          style={{ color: 'var(--color-ink-4)', lineHeight: 1.4 }}
        >
          {FACTOR_HINTS[factor]}
        </span>
        <span
          className="text-[10px] tabular-nums"
          style={{ color: 'var(--color-ink-4)', whiteSpace: 'nowrap' }}
        >
          weight {(data.weight * 100).toFixed(0)}% × value {data.value.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

interface Props {
  open: boolean;
  factors: MaterialityFactors | null;
  score: number | null;
  onClose: () => void;
}

export default function MaterialityDrawer({ open, factors, score, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      data-materiality-drawer
      role="dialog"
      aria-label="Materiality breakdown"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        display: 'flex',
        justifyContent: 'flex-end',
        background: 'rgba(0, 0, 0, 0.35)',
      }}
      onClick={(e) => {
        // Click on backdrop (not panel) closes.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside
        style={{
          width: 'min(440px, 92vw)',
          height: '100%',
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-line)',
          padding: '24px',
          overflowY: 'auto',
          boxShadow: '-12px 0 32px rgba(0, 0, 0, 0.18)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <header className="flex items-start justify-between gap-3">
          <div>
            <div
              className="text-[10px] uppercase tracking-wider"
              style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em' }}
            >
              Materiality breakdown
            </div>
            <div
              className="font-display"
              style={{
                fontSize: '48px',
                lineHeight: 1.05,
                color: 'var(--color-ink)',
                marginTop: '6px',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {score != null ? score.toFixed(1) : '—'}
            </div>
            <div
              className="text-[12px]"
              style={{ color: 'var(--color-ink-3)', marginTop: '2px' }}
            >
              out of 100
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="text-[12px]"
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--color-line)',
              background: 'transparent',
              color: 'var(--color-ink-3)',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </header>

        <div style={{ marginTop: '20px' }}>
          {factors == null ? (
            <div
              className="text-[12px]"
              style={{
                color: 'var(--color-ink-3)',
                padding: '20px',
                border: '1px dashed var(--color-line)',
                borderRadius: '8px',
                textAlign: 'center',
              }}
            >
              Not yet scored — no breakdown available.
            </div>
          ) : (
            <div>
              {FACTOR_ORDER.map((f) => (
                <FactorRow key={f} factor={f} data={factors[f]} />
              ))}
            </div>
          )}
        </div>

        <footer style={{ marginTop: 'auto', paddingTop: '24px' }}>
          <div
            className="text-[10px] uppercase tracking-wider"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em' }}
          >
            Formula
          </div>
          <code
            className="text-[11px] block"
            style={{
              marginTop: '6px',
              color: 'var(--color-ink-3)',
              background: 'var(--color-surface-2)',
              padding: '10px 12px',
              borderRadius: '6px',
              fontFamily:
                'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              lineHeight: 1.5,
            }}
          >
            score = 100 × Σ (weight_i × value_i)
          </code>
          <div
            className="text-[10px]"
            style={{ color: 'var(--color-ink-4)', marginTop: '8px', lineHeight: 1.4 }}
          >
            Weights are tunable. Reviewers can re-rank what counts as material
            by editing the weights config — older signals re-score on demand.
          </div>
        </footer>
      </aside>
    </div>
  );
}
