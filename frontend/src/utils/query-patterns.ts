export type QueryType = 'path' | 'comparison' | 'entity' | 'general';

export function detectQueryType(query: string): QueryType {
  const q = query.toLowerCase().trim();

  // Path: "path between X and Y", "how is X connected to Y"
  if (/\b(path between|connection from|how is .+ (related|connected) to|link between)\b/.test(q))
    return 'path';

  // Comparison: "X vs Y", "compare X and Y"
  if (/\b(compare|vs\.?|versus|differences? between)\b/.test(q))
    return 'comparison';

  // Entity: short query, likely a name lookup
  if (q.split(/\s+/).length <= 3 && !/\b(how|why|what|which|show|list)\b/.test(q))
    return 'entity';

  return 'general';
}

/** Extract entity names from a path query */
export function extractPathEntities(query: string): [string, string] | null {
  const match = query.match(
    /(?:path between|connection from|link between)\s+(.+?)\s+(?:and|to)\s+(.+)/i,
  );
  if (match) return [match[1].trim(), match[2].trim()];
  return null;
}
