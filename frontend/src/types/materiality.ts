/**
 * Loop #20 — Materiality factor types.
 *
 * Mirrors `MaterialityResult.to_dict()` from services/materiality.py.
 * `score = 100 × Σ(weight_i × value_i)`, equivalently `Σ contributions`.
 */
export interface MaterialityFactor {
  input: number | string | null;
  value: number;
  weight: number;
  contribution: number;
}

export interface MaterialityFactors {
  source_tier: MaterialityFactor;
  entity_criticality: MaterialityFactor;
  claim_type: MaterialityFactor;
  recency: MaterialityFactor;
}
