import { describe, it, expect } from 'vitest';
import {
  FACT_CLASS,
  factClassColor,
  factClassSoft,
  deriveFactClass,
  type FactClass,
} from '../helix';

describe('fact_class palette (Helix v8 alignment)', () => {
  it('defines all five classes with glyph + label + theme-var color', () => {
    const classes: FactClass[] = ['reference', 'corporate', 'signal', 'inferred', 'internal'];
    for (const c of classes) {
      expect(FACT_CLASS[c]).toBeTruthy();
      expect(FACT_CLASS[c].glyph).toMatch(/^[RCSIX]$/);
      expect(FACT_CLASS[c].label.length).toBeGreaterThan(0);
      expect(FACT_CLASS[c].color).toContain('var(--fc-');
    }
  });

  it('maps the canonical v8 glyphs', () => {
    expect(FACT_CLASS.reference.glyph).toBe('R');
    expect(FACT_CLASS.corporate.glyph).toBe('C');
    expect(FACT_CLASS.signal.glyph).toBe('S');
    expect(FACT_CLASS.inferred.glyph).toBe('I');
    expect(FACT_CLASS.internal.glyph).toBe('X');
  });

  it('factClassColor / factClassSoft resolve to fc CSS vars', () => {
    expect(factClassColor('reference')).toBe('var(--fc-ref)');
    expect(factClassSoft('signal', 0.16)).toContain('--fc-signal');
    // unknown -> falls back to signal (these are signals by default)
    expect(factClassColor(undefined)).toBe(factClassColor('signal'));
  });
});

describe('deriveFactClass — heuristic over the fields we have today', () => {
  it('maps signal confidence_tier to a fact class', () => {
    expect(deriveFactClass({ confidence_tier: 'confirmed' })).toBe('reference');
    expect(deriveFactClass({ confidence_tier: 'reported' })).toBe('corporate');
    expect(deriveFactClass({ confidence_tier: 'inferred' })).toBe('inferred');
    expect(deriveFactClass({ confidence_tier: 'disputed' })).toBe('signal');
  });

  it('flags internal / contributed sources as internal', () => {
    expect(deriveFactClass({ source_id: 'user_document' })).toBe('internal');
    expect(deriveFactClass({ source_id: 'zs_internal_panel' })).toBe('internal');
  });

  it('maps tier_1 events to reference, else signal', () => {
    expect(deriveFactClass({ source_tier: 'tier_1' })).toBe('reference');
    expect(deriveFactClass({ source_tier: 'tier_3' })).toBe('signal');
  });

  it('defaults to signal when nothing is known (these are signals)', () => {
    expect(deriveFactClass({})).toBe('signal');
  });
});
