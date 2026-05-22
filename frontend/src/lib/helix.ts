/**
 * Helix design tokens — the bespoke CI design language (from helix-core.jsx).
 * Locked dark "war room" palette, OKLCH category hues (fixed L/C, hue only),
 * serif display + mono metadata. Shared across CI surfaces so the look is
 * consistent and there's a single source of truth.
 */
export const HELIX = {
  bg: '#0a0b0e', ink: '#e8eaed', ink2: '#c2c6cf', dim: '#8a8f99',
  faint: '#5a5f69', ghost: '#363a42', panel: '#12141a', panel2: '#181b22',
  panel3: '#1f232b', line: '#23262d', line2: '#2c3038',
  accent: '#5eead4', accent2: '#a78bfa',
  ok: '#34d399', warn: '#fbbf24', bad: '#f87171', hot: '#fb7185',
  serif: "'Instrument Serif', 'Fraunces', Georgia, serif",
  mono: "'JetBrains Mono', 'DM Mono', ui-monospace, monospace",
};

/** Category hue per canonical KBQ tag (matches helix-core CATEGORIES). */
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

/** Tier word for an impact tier (Helix encodes urgency by weight, not hue). */
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
