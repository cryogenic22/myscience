import { FACT_CLASS, deriveFactClass, type FactClass } from '../../lib/helix';

interface Props {
  /** Pass an explicit class, or the fields to derive it from. */
  factClass?: FactClass;
  confidence_tier?: string | null;
  source_tier?: string | null;
  source_id?: string | null;
  size?: number;
  /** Show the class label after the glyph. */
  withLabel?: boolean;
}

/**
 * The Helix v8 fact-class glyph (R/C/S/I/X) — a small coloured square that
 * shows, at a glance, WHERE a signal/fact came from (reference / corporate /
 * signal / inferred / internal). Shared across the Signals DB, Stream, and
 * Digest so provenance is legible everywhere (PB-SL04).
 */
export default function FactClassGlyph({
  factClass,
  confidence_tier,
  source_tier,
  source_id,
  size = 16,
  withLabel = false,
}: Props) {
  const fc: FactClass = factClass
    ?? deriveFactClass({ confidence_tier, source_tier, source_id });
  const meta = FACT_CLASS[fc];
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span
        title={meta.label}
        aria-label={`${meta.label} fact`}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: size, height: size, borderRadius: 4,
          background: meta.color, color: '#fff',
          fontFamily: 'var(--font-mono)', fontSize: size * 0.6, fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {meta.glyph}
      </span>
      {withLabel && (
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9.5, fontWeight: 600,
          letterSpacing: '0.05em', textTransform: 'uppercase', color: meta.color,
        }}>
          {meta.label}
        </span>
      )}
    </span>
  );
}
