/**
 * DataHub · F5 — typed client + stub for the source-onboarding contract.
 *
 * This mirrors the backend L2 service (`services/connector_taxonomy.py`, #245)
 * which already defines the connector-type taxonomy + the onboarding lifecycle
 * state machine — but is NOT yet exposed over HTTP (D-API-1:
 * `GET /hub/connector-types`, `GET/POST /hub/onboarding/{source_id}`).
 *
 * Per `docs/SPEC_DATA_HUB_FRONTEND.md` §4, a frontend loop that needs a missing
 * endpoint builds against a **typed stub** and degrades gracefully; the wiring
 * is then a one-line swap when the endpoint lands. The types here are shaped to
 * the backend dataclasses (`ConnectorType`, `OnboardingRecord`) so that swap is
 * trivial.
 *
 * ⚠️ No network calls yet — `registerSource()` is a local stub that validates
 * the contract and echoes a draft onboarding record. When D-API-1 ships, swap
 * the stub body for `fetch(`${BASE}/hub/onboarding/${id}`, …)`.
 */

// ── Connector taxonomy (mirrors CONNECTOR_TYPE_NAMES in connector_taxonomy.py) ──

/** The six connector kinds a source can declare (DB-backed taxonomy). */
export type ConnectorTypeName =
  | 'API_REST'
  | 'RSS'
  | 'CSV_FILE'
  | 'WEB_SCRAPE'
  | 'WAREHOUSE'
  | 'MANUAL';

export interface ConnectorTypeOption {
  name: ConnectorTypeName;
  label: string;
  /** Short human description of how the source is fetched. */
  description: string;
  /** The config fields this connector kind needs (drives the form). */
  configFields: Array<{ key: string; label: string; placeholder: string; required: boolean }>;
}

/**
 * The five source kinds the wizard onboards (SPEC §5 F5). `MANUAL` is the
 * fallback / no-automation path; the wizard foregrounds the five automated
 * kinds but the taxonomy is the source of truth.
 */
export const CONNECTOR_TYPES: ConnectorTypeOption[] = [
  {
    name: 'API_REST',
    label: 'REST API',
    description: 'A JSON/XML HTTP endpoint polled on a schedule.',
    configFields: [
      { key: 'base_url', label: 'Base URL', placeholder: 'https://api.example.com/v1', required: true },
      { key: 'records_path', label: 'Records JSONPath', placeholder: 'data.results', required: false },
      { key: 'auth_header', label: 'Auth header (optional)', placeholder: 'Authorization: Bearer …', required: false },
    ],
  },
  {
    name: 'RSS',
    label: 'RSS / Atom feed',
    description: 'A syndication feed (press releases, journal alerts).',
    configFields: [
      { key: 'feed_url', label: 'Feed URL', placeholder: 'https://example.com/feed.xml', required: true },
    ],
  },
  {
    name: 'CSV_FILE',
    label: 'CSV file',
    description: 'A delimited file (local upload or a stable URL).',
    configFields: [
      { key: 'file_url', label: 'File URL', placeholder: 'https://example.com/data.csv', required: true },
      { key: 'delimiter', label: 'Delimiter', placeholder: ',', required: false },
    ],
  },
  {
    name: 'WEB_SCRAPE',
    label: 'Web scrape',
    description: 'A structured HTML page extracted with selectors.',
    configFields: [
      { key: 'page_url', label: 'Page URL', placeholder: 'https://example.com/listing', required: true },
      { key: 'row_selector', label: 'Row selector', placeholder: 'table.results tr', required: false },
    ],
  },
  {
    name: 'WAREHOUSE',
    label: 'Warehouse / SQL',
    description: 'A query against a connected data warehouse.',
    configFields: [
      { key: 'connection', label: 'Connection name', placeholder: 'snowflake_prod', required: true },
      { key: 'query', label: 'SQL query', placeholder: 'SELECT … FROM …', required: true },
    ],
  },
];

// ── Trust tier (mirrors source_registry.py tiers: 1 gold / 2 curated / 3 derived) ──

export type TrustTier = 1 | 2 | 3;

export const TRUST_TIERS: Array<{ tier: TrustTier; label: string; hint: string }> = [
  { tier: 1, label: 'Tier 1 — regulatory / registry (gold)', hint: 'Authoritative primary source (e.g. FDA, SEC, ClinicalTrials.gov).' },
  { tier: 2, label: 'Tier 2 — curated literature / ontology', hint: 'Curated secondary source (e.g. PubMed, MeSH).' },
  { tier: 3, label: 'Tier 3 — derived / aggregated', hint: 'Derived or third-party-aggregated data.' },
];

// ── Onboarding lifecycle (mirrors ONBOARDING_STATUSES in connector_taxonomy.py) ──

export type OnboardingStatus = 'draft' | 'test' | 'staged' | 'prod' | 'paused' | 'retired';

/** The forward "happy path" the wizard visualises. */
export const LIFECYCLE_PATH: OnboardingStatus[] = ['draft', 'test', 'staged', 'prod'];

// ── The contract a source must declare to be onboarded ──

export interface FieldMapping {
  /** The field name in the source payload. */
  source_field: string;
  /** The canonical entity field it maps to. */
  target_field: string;
}

export interface SourceContract {
  /** Trust tier — required (the wizard blocks without it). */
  trust_tier: TrustTier | null;
  /**
   * Must-capture fields — the fields that MUST be present on every record or
   * the row is rejected (conservation: no silent-loss). Required: at least one.
   */
  must_capture: string[];
  license: string | null;
}

export interface OnboardingDraft {
  source_key: string;
  label: string;
  connector_type: ConnectorTypeName;
  config: Record<string, string>;
  mappings: FieldMapping[];
  contract: SourceContract;
}

/** Shaped to the backend `OnboardingRecord.to_dict()`. */
export interface OnboardingRecordDTO {
  source_id: string;
  status: OnboardingStatus;
  owner: string | null;
  contact: string | null;
  go_live_date: string | null;
  escalation: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RegisterResult {
  ok: boolean;
  record?: OnboardingRecordDTO;
  /** Validation errors that block registration (the wizard surfaces these). */
  errors: string[];
  /**
   * TRUE when the contract was validated locally but NOT persisted to the
   * backend (the write-path is still pending — see registerSource). The wizard
   * MUST show an honest "preview, not persisted" state for these, never a green
   * "registered" confirmation. Absent/false ⇒ a real backend write succeeded.
   */
  preview?: boolean;
}

/**
 * Validate that a draft declares a complete contract. Mirrors the backend's
 * "every onboarded source must declare a contract or it blocks" rule (SPEC §5
 * F5 acceptance). Pure — unit-testable without a network.
 */
export function validateContract(draft: OnboardingDraft): string[] {
  const errors: string[] = [];
  if (!draft.source_key.trim()) errors.push('A source key is required.');
  if (!draft.label.trim()) errors.push('A display label is required.');

  // Required connector config fields.
  const typeDef = CONNECTOR_TYPES.find((t) => t.name === draft.connector_type);
  for (const f of typeDef?.configFields ?? []) {
    if (f.required && !(draft.config[f.key] ?? '').trim()) {
      errors.push(`${f.label} is required for a ${typeDef?.label} source.`);
    }
  }

  // The contract gate — trust tier + at least one must-capture field.
  if (draft.contract.trust_tier === null) {
    errors.push('Declare a trust tier — an onboarded source must state its provenance tier.');
  }
  const captures = draft.contract.must_capture.filter((c) => c.trim());
  if (captures.length === 0) {
    errors.push('Declare at least one must-capture field — rows missing it are rejected (no silent loss).');
  }
  return errors;
}

/**
 * Validate a source's contract and PREVIEW the draft record the backend will
 * return — it does NOT persist anything yet.
 *
 * ⚠️ PREVIEW-ONLY. The real write-path needs a two-stage backend flow
 * (POST /sources to register the source, then POST /hub/onboarding/{id} for the
 * lifecycle) AND backend storage for the full contract (config/mappings/
 * trust_tier/must_capture/license). StartOnboardingBody silently ignores those
 * fields today, so a naive POST would 201 while dropping the contract this
 * wizard exists to enforce — a silent conservation violation. Until the
 * cross-lane contract storage lands (COORDINATION §8.1), this returns
 * `preview: true` so the wizard tells the truth: "validated, not persisted".
 * When the backend is ready, do the POST and return `preview: false`.
 */
export async function registerSource(draft: OnboardingDraft): Promise<RegisterResult> {
  const errors = validateContract(draft);
  if (errors.length > 0) {
    return { ok: false, errors };
  }
  const now = new Date().toISOString();
  // TODO(write-path): two-stage POST /sources → POST /hub/onboarding/{id} once
  // the backend persists the full contract; then drop `preview`.
  return {
    ok: true,
    errors: [],
    preview: true, // validated locally; nothing persisted to the backend yet
    record: {
      source_id: draft.source_key,
      status: 'draft',
      owner: null,
      contact: null,
      go_live_date: null,
      escalation: null,
      created_at: now,
      updated_at: now,
    },
  };
}
