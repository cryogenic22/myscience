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
  adverse_event: 'Adverse Event',
  trial_outcome: 'Trial Outcome',
  trial_location: 'Trial Location',
  drug_label: 'Drug Label',
};

/** Connectivity descriptors */
export const CONNECTIVITY_LABELS: Record<string, string> = {
  sparse: 'Few connections',
  moderate: 'Moderate connectivity',
  dense: 'Well connected',
  hub: 'Highly connected hub',
};

/** Change types → user-facing descriptions */
export const CHANGE_TYPE_LABELS: Record<string, string> = {
  manual_edit: 'Manual edit',
  enrich_company_from_sponsor: 'Company linked from trial sponsor',
  enrich_brand_from_label: 'Brand name from FDA label',
  enrich_brand_from_milestone: 'Brand name from regulatory milestone',
  enrich_approval_from_milestone: 'Approval date from milestone',
  backfill_ta_link: 'Therapeutic area linked',
  backfill_label: 'Label backfilled',
  auto_curate_run: 'Automated curation',
  created: 'Created',
  drug_name_cleaned: 'Drug name cleaned',
  company_merged: 'Company merged',
  company_excluded: 'Non-company excluded',
  biomarker_extraction: 'Biomarker extracted',
};

/** Database column names → user-facing field labels */
export const FIELD_LABELS: Record<string, string> = {
  generic_name: 'Generic Name',
  brand_name: 'Brand Name',
  company_id: 'Company',
  mechanism_id: 'Mechanism',
  therapeutic_area_id: 'Therapeutic Area',
  approval_date: 'Approval Date',
  patent_expiry_date: 'Patent Expiry',
  supply_status: 'Supply Status',
  record_status: 'Record Status',
  source_api: 'Source',
  source_authority: 'Authority',
  source_url: 'Source URL',
  retrieved_at: 'Retrieved',
  created_at: 'Created',
  updated_at: 'Updated',
  last_verified_at: 'Last Verified',
  content_hash: 'Content Hash',
  quality_score: 'Quality Score',
  nda_number: 'NDA Number',
  nct_id: 'NCT ID',
  pmid: 'PMID',
  mesh_id: 'MeSH ID',
  scope_note: 'Scope Note',
  official_title: 'Title',
  sponsor_name: 'Sponsor',
  enrollment_target: 'Enrollment',
  start_date: 'Start Date',
  primary_completion_date: 'Primary Completion',
  completion_date: 'Completion Date',
  study_type: 'Study Type',
  conditions: 'Conditions',
  phase: 'Phase',
  status: 'Status',
  ticker: 'Ticker',
  cik: 'CIK',
  region: 'Region',
  country: 'Country',
  market_cap_tier: 'Market Cap',
  dosage_form: 'Dosage Form',
  route: 'Route',
  marketing_status: 'Marketing Status',
  mesh_terms: 'MeSH Terms',
  journal: 'Journal',
  publication_date: 'Publication Date',
  title: 'Title',
  name: 'Name',
  label: 'Label',
};

/** Generic display name resolver — tries all maps, falls back to title-casing */
export function displayName(key: string): string {
  return (
    FIELD_LABELS[key] ??
    LINK_TYPE_LABELS[key] ??
    QUALITY_CHECK_LABELS[key] ??
    SOURCE_LABELS[key] ??
    ENTITY_TYPE_LABELS[key] ??
    CONNECTIVITY_LABELS[key] ??
    CHANGE_TYPE_LABELS[key] ??
    key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/** Returns true if the string looks like a UUID (should be hidden from users) */
export function isUUID(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
