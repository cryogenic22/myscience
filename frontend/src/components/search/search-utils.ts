import type { SearchResult } from '../../api';

export type SearchViewMode = 'cards' | 'grid' | 'list';
export type SortMode = 'relevance' | 'quality' | 'recent';
export type GraphFocus = { id: string; type: string; label: string };

export const ENTITY_TYPES = [
  { key: 'drug', label: 'Drugs' },
  { key: 'trial', label: 'Trials' },
  { key: 'literature', label: 'Literature' },
  { key: 'company', label: 'Companies' },
  { key: 'therapeutic_area', label: 'Therapeutic Areas' },
] as const;

export const TYPE_CONFIG: Record<string, { color: string; bgVar: string; label: string }> = {
  drug:             { color: 'var(--color-drug)',       bgVar: 'rgba(37, 99, 235, 0.08)',  label: 'Drug' },
  trial:            { color: 'var(--color-trial)',      bgVar: 'rgba(13, 148, 136, 0.08)', label: 'Trial' },
  literature:       { color: 'var(--color-literature)', bgVar: 'rgba(5, 150, 105, 0.08)',  label: 'Literature' },
  company:          { color: 'var(--color-company)',    bgVar: 'rgba(217, 119, 6, 0.08)',  label: 'Company' },
  mechanism:        { color: 'var(--color-mechanism)',  bgVar: 'rgba(124, 58, 237, 0.08)', label: 'Mechanism' },
  therapeutic_area: { color: 'var(--color-ta)',         bgVar: 'rgba(225, 29, 72, 0.08)',  label: 'Therapeutic Area' },
};

export const VIEW_OPTIONS: Array<{ value: SearchViewMode; label: string }> = [
  { value: 'cards', label: 'Cards' },
  { value: 'grid', label: 'Grid' },
  { value: 'list', label: 'List' },
];

export const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: 'relevance', label: 'Best match' },
  { value: 'quality', label: 'Highest quality' },
  { value: 'recent', label: 'Most recent' },
];

export const PAGE_SIZE = 30;

export function prettyType(value: string): string {
  return value.replace(/_/g, ' ').toLowerCase();
}

export function truncateValue(value: unknown, limit: number): string {
  const asText = String(value);
  return asText.length > limit ? `${asText.slice(0, limit - 2)}..` : asText;
}

export function formatDate(value: unknown): string {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function normalizeFacetValue(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, ' ');
}

export function extractTherapeuticAreasFromResult(result: SearchResult): string[] {
  const values: string[] = [];
  if (result.entity_type === 'therapeutic_area') {
    values.push(result.title);
  }
  const keys = ['therapeutic_area', 'therapeutic_area_name', 'therapy_area', 'indication', 'disease_area'];
  for (const key of keys) {
    const raw = result.metadata?.[key];
    if (typeof raw === 'string') {
      const chunks = raw.split(/[;,|]/).map((item) => item.trim()).filter(Boolean);
      values.push(...chunks);
    }
    if (Array.isArray(raw)) {
      values.push(...raw.filter((item): item is string => typeof item === 'string').map((item) => item.trim()).filter(Boolean));
    }
  }
  const deduped = new Map<string, string>();
  for (const value of values) {
    const normalized = normalizeFacetValue(value);
    if (!normalized) continue;
    if (!deduped.has(normalized)) deduped.set(normalized, value);
  }
  return [...deduped.values()];
}

export function getResultSnippet(result: SearchResult): string | null {
  const primarySnippet = typeof result.snippet === 'string' ? result.snippet.trim() : '';
  if (primarySnippet && primarySnippet.toLowerCase() !== result.title.trim().toLowerCase()) {
    return truncateValue(primarySnippet, 220);
  }

  const fallbackKeys = ['description', 'summary', 'abstract', 'content', 'text', 'narrative', 'excerpt'];
  for (const key of fallbackKeys) {
    const value = result.metadata?.[key];
    if (typeof value === 'string') {
      const normalized = value.trim();
      if (normalized.length > 18 && !/^https?:\/\//i.test(normalized)) {
        return truncateValue(normalized, 220);
      }
    }
    if (Array.isArray(value)) {
      const merged = value.filter((item): item is string => typeof item === 'string').join(' ').trim();
      if (merged.length > 18) return truncateValue(merged, 220);
    }
  }

  return null;
}

export function getSourcePublicationDate(metadata: Record<string, unknown> | undefined): string | null {
  if (!metadata) return null;
  const dateKeys = [
    'publication_date',
    'published_at',
    'published_date',
    'date_published',
    'article_date',
    'source_date',
  ];
  for (const key of dateKeys) {
    const normalized = normalizeDateValue(metadata[key]);
    if (normalized) return normalized;
  }
  return null;
}

function normalizeDateValue(value: unknown): string | null {
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return null;
    const timestamp = Date.parse(text);
    return Number.isNaN(timestamp) ? null : text;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
  }
  return null;
}

export function resultFingerprint(result: SearchResult): string {
  return [
    result.entity_id,
    result.entity_type,
    result.title,
    result.provenance?.source_api ?? '',
    result.provenance?.retrieved_at ?? '',
    result.similarity.toFixed(6),
  ].join('|');
}

export function toTimestamp(value: unknown): number {
  if (!value) return 0;
  const ts = new Date(String(value)).getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

export function safeTileValue(value: string): string {
  return truncateValue(value, 26);
}

export function extractPreviewContent(result: SearchResult): string {
  const candidates: string[] = [];
  if (result.snippet && result.snippet.trim().length > 0) {
    candidates.push(result.snippet.trim());
  }

  const preferredKeys = ['content', 'abstract', 'summary', 'description', 'text', 'narrative', 'excerpt'];
  for (const key of preferredKeys) {
    const value = result.metadata?.[key];
    if (typeof value === 'string' && value.trim().length > 0 && !/^https?:\/\//i.test(value.trim())) {
      candidates.push(value.trim());
    }
    if (Array.isArray(value)) {
      const merged = value.filter((item): item is string => typeof item === 'string').join(' ');
      if (merged.trim().length > 0) candidates.push(merged.trim());
    }
  }

  for (const value of Object.values(result.metadata ?? {})) {
    if (typeof value !== 'string') continue;
    const text = value.trim();
    if (!text || /^https?:\/\//i.test(text)) continue;
    candidates.push(text);
    if (candidates.length > 5) break;
  }

  const best = candidates.find((item) => item.length > 80) ?? candidates[0] ?? '';
  if (!best) return 'No content preview available in indexed data for this result.';
  return truncateValue(best, 760);
}

export function getRelatedDocuments(result: SearchResult): string[] {
  const urls = new Set<string>();
  const sourceUrl = result.provenance?.source_url;
  if (typeof sourceUrl === 'string') {
    extractUrls(sourceUrl, urls);
  }

  for (const value of Object.values(result.metadata ?? {})) {
    if (typeof value === 'string') {
      extractUrls(value, urls);
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === 'string') extractUrls(item, urls);
      }
    }
  }
  return [...urls].slice(0, 6);
}

export function getRelatedNodes(result: SearchResult): Array<{ key: string; label: string; value: string }> {
  const preferredKeys = [
    'drug_name',
    'company_name',
    'mechanism_name',
    'therapeutic_area',
    'trial_phase',
    'drug_id',
    'company_id',
    'mechanism_id',
    'therapeutic_area_id',
  ];
  const rows: Array<{ key: string; label: string; value: string }> = [];
  for (const key of preferredKeys) {
    const raw = result.metadata?.[key];
    if (raw === null || raw === undefined) continue;
    const text = String(raw).trim();
    if (!text || /^https?:\/\//i.test(text)) continue;
    rows.push({
      key,
      label: prettyType(key),
      value: text,
    });
  }
  if (rows.length === 0) {
    rows.push({
      key: 'title',
      label: 'entity',
      value: result.title,
    });
  }
  const unique = new Map<string, { key: string; label: string; value: string }>();
  for (const row of rows) {
    const dedupeKey = `${row.key}:${row.value.toLowerCase()}`;
    if (!unique.has(dedupeKey)) unique.set(dedupeKey, row);
  }
  return [...unique.values()];
}

function extractUrls(text: string, into: Set<string>) {
  const matches = text.match(/https?:\/\/[^\s,;]+/gi);
  if (!matches) return;
  for (const match of matches) {
    into.add(match.replace(/[)\].,]+$/, ''));
  }
}
