/**
 * Helix design tokens — semantic mappings for CI signal cards.
 *
 * Loop D1.5 (30 May 2026): refactored from a parallel hardcoded dark
 * palette to read from the global CSS variable system. This was the
 * root cause of the "sidebar light, main dark" theme-split bug — when
 * the F1 theme toggle moved the page into ZS, the shell honored it but
 * components importing HELIX still saw hardcoded `#0a0b0e` etc.
 *
 * What stays here:
 *   - Semantic category metadata (CAT_HUE, CAT_LABEL, IMPACT_TONE, IMPACT_WORD)
 *     — those are domain meanings, not theme.
 *   - Per-category OKLCH color helpers — visually identifiable hues for
 *     financial / governance / strategic / etc. signals.
 *
 * What changed:
 *   - All surface/text/font tokens now route through `var(--color-*)` and
 *     `var(--font-*)`. They theme-react automatically.
 *   - The unloaded `'Instrument Serif'` / `'JetBrains Mono'` references are
 *     gone — replaced with the actually-loaded display + mono families.
 */

/** Surface/text/font references — all theme-aware via CSS variables. */
export const HELIX = {
  bg:     'var(--color-bg)',
  ink:    'var(--color-ink)',
  ink2:   'var(--color-ink-2)',
  dim:    'var(--color-ink-3)',
  faint:  'var(--color-ink-4)',
  ghost:  'var(--color-ink-4)',
  panel:  'var(--color-surface)',
  panel2: 'var(--color-surface-2)',
  panel3: 'var(--color-surface-3)',
  line:   'var(--color-line)',
  line2:  'var(--color-line-2)',
  accent: 'var(--color-accent)',
  accent2:'var(--color-accent)',
  ok:     'var(--color-green)',
  warn:   'var(--color-amber)',
  bad:    'var(--color-red)',
  hot:    'var(--color-red)',
  // Loaded families only — Fraunces (display) + DM Mono (technical).
  serif:  'var(--font-display)',
  mono:   'var(--font-mono)',
};

/** Category hue per canonical KBQ tag — semantic, theme-independent. */
export const CAT_HUE: Record<string, number> = {
  financial: 220, governance: 200, strategic: 270, clinical: 170,
  product: 25, regulatory: 45, m_and_a: 320, pricing_access: 145,
  ai_digital: 250, esg_supply: 350,
};

export const catColor = (tag: string | undefined): string =>
  `oklch(0.72 0.16 ${CAT_HUE[tag ?? ''] ?? 200})`;
export const catSoft = (tag: string | undefined, alpha = 0.12): string =>
  `oklch(0.72 0.16 ${CAT_HUE[tag ?? ''] ?? 200} / ${alpha})`;

/** Category label for a tag (Title Case). */
export const CAT_LABEL: Record<string, string> = {
  financial: 'Financial', governance: 'Governance', strategic: 'Strategic',
  clinical: 'Clinical', product: 'Product', regulatory: 'Regulatory',
  m_and_a: 'M&A', pricing_access: 'Pricing & Access', ai_digital: 'AI & Digital',
  esg_supply: 'ESG & Supply',
};

export const IMPACT_TONE: Record<string, string> = {
  high: HELIX.bad, medium: HELIX.warn, low: HELIX.faint,
};

/** Tier word for an impact tier (encodes urgency by weight, not hue). */
export const IMPACT_WORD: Record<string, string> = {
  high: 'ACT', medium: 'WATCH', low: 'AMBIENT',
};

export function fmtAge(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const secs = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}
