/**
 * Search Query Classifier — categorizes user search queries
 * to drive result layout and graph behavior.
 */

export type SearchQueryType =
  | 'entity'
  | 'relationship'
  | 'path'
  | 'comparison'
  | 'cluster'
  | 'exploratory';

/**
 * Classifies a free-text search query into one of six categories.
 * Used to adjust result card rendering and auto-expand graph behavior.
 */
export function classifySearchQuery(query: string): SearchQueryType {
  const q = query.toLowerCase().trim();

  if (/\b(path between|connection from|how is .+ (related|connected) to|link between)\b/.test(q)) {
    return 'path';
  }
  if (/\b(compare|vs\.?|versus|differences? between)\b/.test(q)) {
    return 'comparison';
  }
  if (/\b(clusters?|competitive map|market (map|segments)|who competes)\b/.test(q)) {
    return 'cluster';
  }
  if (/\b(drugs? (that|which)|companies? (that|with)|trials? (for|investigating))\b/.test(q)) {
    return 'relationship';
  }
  if (/\b(targeting|linked to|associated with|owned by)\b/.test(q)) {
    return 'relationship';
  }
  if (q.split(/\s+/).length <= 4 && !/\b(how|why|when|where|which|what|who)\b/.test(q)) {
    return 'entity';
  }
  return 'exploratory';
}
