/**
 * @mz/design-tokens — runtime token access for TS consumers.
 *
 * Tokens are also emitted as CSS variables (see ./tokens.css). Components
 * should prefer the CSS variable surface (`var(--mz-color-text-primary)`)
 * for styling. This module is for code paths that need a runtime value
 * (e.g. inline SVG fill, animation step calculation, theme switching).
 */

import tokensJson from './tokens.json' with { type: 'json' };

export type Theme = 'light' | 'dark';
export type Density = 'compact' | 'comfortable' | 'spacious';
export type Module = 'research' | 'ci' | 'regulatory';
export type ConfidenceTier = 'confirmed' | 'reported' | 'inferred' | 'disputed';
export type ImpactTier = 'high' | 'medium' | 'low';

export const tokens = tokensJson as typeof tokensJson;

/**
 * Resolve a tier color string. Returns a CSS color value.
 */
export function tierColor(
  kind: 'confidence' | 'impact',
  tier: ConfidenceTier | ImpactTier,
  theme: Theme = 'light',
): string {
  const map: Record<string, string> = {
    'confidence.confirmed': tokens.color.semantic.success[theme],
    'confidence.reported':  tokens.color.neutral[theme]['text-secondary'],
    'confidence.inferred':  tokens.color.semantic.warning[theme],
    'confidence.disputed':  tokens.color.semantic.danger[theme],
    'impact.high':          tokens.color.semantic.danger[theme],
    'impact.medium':        tokens.color.semantic.warning[theme],
    'impact.low':           tokens.color.neutral[theme]['text-tertiary'],
  };
  return map[`${kind}.${tier}`] ?? tokens.color.neutral[theme]['text-tertiary'];
}

/**
 * Resolve a module accent color. Returns a CSS color value.
 */
export function moduleAccent(module: Module, theme: Theme = 'light'): string {
  return tokens.color.accent[module][theme];
}

/**
 * CSS-variable-name helper. Use as `cssVar('color-text-primary')` →
 * `var(--mz-color-text-primary)`. Prefer this over hard-coded var names
 * so the prefix can be evolved centrally.
 */
export function cssVar(name: string, fallback?: string): string {
  return fallback ? `var(--mz-${name}, ${fallback})` : `var(--mz-${name})`;
}
