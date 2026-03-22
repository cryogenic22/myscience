export const PRODUCT_NAME = 'Market Zero';
export const PRODUCT_SUBTITLE = 'Pharma Intelligence Platform';
export const PRODUCT_TAGLINE = 'Evidence-grounded intelligence for pharma strategy';

// ── Display name translation layer ──
// Maps internal identifiers to human-readable labels. Every backend constant
// that could appear in the UI should have an entry here.

/** Link type constants → user-facing labels */
export const LINK_TYPE_LABELS: Record<string, string> = {
  EVIDENCE_FOR: 'Supporting literature',
  INVESTIGATES: 'Clinical trials',
  OWNS: 'Manufacturer',
  SPONSORS: 'Trial sponsor',
  IN_THERAPEUTIC_AREA: 'Therapeutic area',
  TARGETS_MECHANISM: 'Mechanism of action',
  MENTIONED_IN: 'Mentioned in',
  COMPETES_WITH: 'Competitor',
  HAS_PATENT: 'Patent',
  HAS_MILESTONE: 'Regulatory milestone',
  HAS_OUTCOME: 'Trial outcome',
  HAS_LABEL: 'Drug label',
  SHORTAGE_AFFECTS: 'Supply shortage',
  LOCATED_AT: 'Study site',
  LED_BY: 'Lead investigator',
  AUTHORED_BY: 'Author',
  HAS_PRIMARY_ENDPOINT: 'Primary endpoint',
  HAS_SECONDARY_ENDPOINT: 'Secondary endpoint',
  HAS_ADVERSE_EVENT: 'Safety event',
};

/** Quality check code → plain-language description */
export const QUALITY_CHECK_LABELS: Record<string, string> = {
  drug_completeness_core: 'Core field completeness',
  drug_completeness_extended: 'Extended field completeness',
  drug_company_link: 'Manufacturer linked',
  drug_cross_source: 'Cross-source validation',
  drug_embedding_coverage: 'Search embedding',
  drug_freshness: 'Data freshness',
  drug_naming_consistency: 'Name consistency',
  trial_completeness: 'Trial data completeness',
  trial_freshness: 'Trial data freshness',
  company_completeness: 'Company data completeness',
  company_cross_source: 'Company cross-source',
  literature_completeness: 'Publication completeness',
  literature_freshness: 'Publication freshness',
  event_completeness: 'Event completeness',
};

/** Source API constants → user-facing source names */
export const SOURCE_LABELS: Record<string, string> = {
  clinical_trials_gov: 'ClinicalTrials.gov',
  pubmed: 'PubMed',
  fda_orange_book: 'FDA Orange Book',
  openfda_faers: 'FDA Safety Reports',
  openfda_labels: 'FDA Drug Labels',
  fda_shortages: 'FDA Drug Shortages',
  sec_edgar: 'SEC EDGAR',
  mesh_ontology: 'MeSH Ontology',
  pmc: 'PubMed Central',
  backfill: 'Internal enrichment',
  backfill_linkage: 'Internal linkage',
  seed: 'Seed data',
  biomarker_extraction: 'Biomarker extraction',
};

/** Entity type constants → user-facing labels */
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  drug: 'Drug',
  company: 'Company',
  trial: 'Clinical Trial',
  literature: 'Publication',
  mechanism: 'Mechanism of Action',
  therapeutic_area: 'Therapeutic Area',
  event: 'Market Event',
  investigator: 'Investigator',
  patent: 'Patent',
  biomarker: 'Biomarker',
};

/** Connectivity descriptors */
export const CONNECTIVITY_LABELS: Record<string, string> = {
  sparse: 'Few connections',
  moderate: 'Moderate connectivity',
  dense: 'Well connected',
  hub: 'Highly connected hub',
};

/** Generic display name resolver — tries all maps, falls back to title-casing */
export function displayName(key: string): string {
  return (
    LINK_TYPE_LABELS[key] ??
    QUALITY_CHECK_LABELS[key] ??
    SOURCE_LABELS[key] ??
    ENTITY_TYPE_LABELS[key] ??
    CONNECTIVITY_LABELS[key] ??
    key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/** Returns true if the string looks like a UUID (should be hidden from users) */
export function isUUID(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
