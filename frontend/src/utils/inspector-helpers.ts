/**
 * Pure utility functions for the InspectorPanel.
 * No side effects, no API calls — just data transformation.
 */

import type { EntityLink } from '../api';

/* ── Property display labels ─────────────────────────────── */

const PROP_LABELS: Record<string, string> = {
  generic_name: 'Generic Name',
  brand_name: 'Brand Name',
  mechanism_name: 'Mechanism',
  company_name: 'Company',
  therapeutic_area: 'Therapeutic Area',
  approval_date: 'Approval Date',
  supply_status: 'Supply Status',
  phase: 'Phase',
  status: 'Status',
  sponsor_name: 'Sponsor',
  enrollment_target: 'Enrollment',
  start_date: 'Start Date',
  conditions: 'Conditions',
  ticker: 'Ticker',
  country: 'Country',
  pmid: 'PMID',
  journal: 'Journal',
  publication_date: 'Publication Date',
  patent_number: 'Patent Number',
  patent_expiry_date: 'Patent Expiry',
  nct_id: 'NCT ID',
  title: 'Title',
  abstract: 'Abstract',
  authors: 'Authors',
  description: 'Description',
  indication: 'Indication',
};

/** Keys that should be hidden from property display */
const SKIP_SUFFIXES = ['_id', '_embedding'];
const SKIP_KEYS = new Set([
  'id', 'entity_id', 'entity_type', 'embedding', 'content_hash',
  'etl_run_id', 'source_url', 'retrieved_at', 'created_at',
  'updated_at', 'last_verified_at', 'record_status', 'quality_score',
]);

/** Human-readable label for a property key */
export function propertyLabel(key: string): string {
  if (PROP_LABELS[key]) return PROP_LABELS[key];
  // Convert snake_case to Title Case
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Format a property value for display */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '--';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') {
    // Try to detect ISO dates
    if (/^\d{4}-\d{2}-\d{2}(T|$)/.test(value)) {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        return d.toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        });
      }
    }
    if (value.length > 120) return value.slice(0, 117) + '...';
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '--';
    // Try to join short string arrays
    if (value.every((v) => typeof v === 'string') && value.length <= 5) {
      const joined = value.join(', ');
      if (joined.length <= 120) return joined;
    }
    return `${value.length} items`;
  }
  return String(value);
}

/** Check if a value looks like a UUID */
function isUUID(value: unknown): boolean {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
  );
}

/** Should this key be hidden from display? */
function shouldSkipKey(key: string): boolean {
  if (key.startsWith('_')) return true;
  if (SKIP_KEYS.has(key)) return true;
  for (const suffix of SKIP_SUFFIXES) {
    if (key.endsWith(suffix)) return true;
  }
  return false;
}

export interface DisplayProperty {
  key: string;
  label: string;
  value: string;
}

/** Filter entity properties for display, removing internal fields */
export function filterProperties(
  entity: Record<string, unknown>,
): DisplayProperty[] {
  return Object.entries(entity)
    .filter(([key, val]) => !shouldSkipKey(key) && !isUUID(val))
    .map(([key, val]) => ({
      key,
      label: propertyLabel(key),
      value: formatValue(val),
    }))
    .filter((p) => p.value !== '--');
}

export interface LinkGroup {
  entityType: string;
  linkTypes: string[];
  links: EntityLink[];
  sampleLabels: Array<{ entityId: string; entityType: string; label: string }>;
}

/**
 * Group links by the "other" entity type relative to the inspected entity.
 * For each group, collect link types and sample labels.
 */
export function groupLinksByType(
  links: EntityLink[],
  currentEntityId: string,
): LinkGroup[] {
  const groups = new Map<string, { linkTypes: Set<string>; links: EntityLink[] }>();

  for (const link of links) {
    const isSource = link.source_entity_id === currentEntityId;
    const otherType = isSource ? link.target_entity_type : link.source_entity_type;

    let group = groups.get(otherType);
    if (!group) {
      group = { linkTypes: new Set(), links: [] };
      groups.set(otherType, group);
    }
    group.linkTypes.add(link.link_type);
    group.links.push(link);
  }

  return Array.from(groups.entries())
    .map(([entityType, { linkTypes, links: groupLinks }]) => {
      // Extract sample labels (up to 3)
      const sampleLabels = groupLinks.slice(0, 3).map((link) => {
        const isSource = link.source_entity_id === currentEntityId;
        return {
          entityId: isSource ? link.target_entity_id : link.source_entity_id,
          entityType: isSource ? link.target_entity_type : link.source_entity_type,
          label: (isSource ? link.target_label : link.source_label) || 'Unknown',
        };
      });

      return {
        entityType,
        linkTypes: Array.from(linkTypes),
        links: groupLinks,
        sampleLabels,
      };
    })
    .sort((a, b) => b.links.length - a.links.length);
}

/** Evidence link types that indicate literature/trial connections */
const EVIDENCE_LINK_TYPES = new Set([
  'EVIDENCE_FOR',
  'INVESTIGATES',
  'MENTIONED_IN',
  'CITED_IN',
  'REFERENCES',
]);

/** Extract evidence links (literature + trial connections) */
export function extractEvidenceLinks(
  links: EntityLink[],
  currentEntityId: string,
): Array<{ label: string; linkType: string; entityId: string; entityType: string }> {
  return links
    .filter((link) => EVIDENCE_LINK_TYPES.has(link.link_type))
    .map((link) => {
      const isSource = link.source_entity_id === currentEntityId;
      return {
        label: (isSource ? link.target_label : link.source_label) || 'Untitled',
        linkType: link.link_type,
        entityId: isSource ? link.target_entity_id : link.source_entity_id,
        entityType: isSource ? link.target_entity_type : link.source_entity_type,
      };
    });
}
