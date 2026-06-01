"""Dossier Knowledge Base (KB1) — persisted, versioned, evidence-grounded.

The dossier is the keystone artifact: a *good* dossier is what makes the
downstream synthesis, scenarios, and war-gaming worth anything. Today's
`services/dossier.py` is a read-only view recomputed on every page load —
ephemeral, unversioned, and never handed to the simulation. This module is
the durable knowledge base behind it.

What it does:
  * ASSEMBLE an 8-domain dossier FROM the facts ledger (services/facts_ledger),
    routing each fact to a ZS decision domain, carrying its fact_class
    (reference/corporate/signal/inferred) and provenance.
  * SCORE coverage per domain (complete / in_progress / gap) so thin domains
    surface as gaps that drive the sense layer's collection priorities.
  * PERSIST each assembly as an immutable, VERSIONED snapshot
    (dossier_snapshots, migration 072) — append-only via superseded_by. This
    is the "knowledge base of dossiers": history, drift, and reuse.

The persisted `domains` payload is exactly the list[DomainView] the
EngagementDossierPage (F7) renders — assembly is server-side, the UI is dumb.

Temporal note: assembly goes through facts_as_of(), which already understands
anticipatory facts. Passing a future `as_of` (KB5) yields a forward-looking
dossier for war-gaming, for free.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Errors ─────────────────────────────────────────────────────────


class EngagementNotFound(LookupError):
    """No engagement with the given id (can't assemble a dossier for it)."""


# ── Domain model ───────────────────────────────────────────────────


# The 8 ZS decision domains, in render order. Mirrors DOSSIER_DOMAINS in
# frontend/src/pages/EngagementDossierPage.tsx — keep in sync.
DOSSIER_DOMAINS: tuple[str, ...] = (
    "disease_and_patient",
    "clinical_profile",
    "competitive",
    "pricing_and_access",
    "commercial_operational",
    "hcp_and_patient",
    "pipeline_and_macro",
    "wargame_specific",
)

VALID_FACT_CLASSES = ("reference", "corporate", "signal", "inferred")

# Default per-domain priority. Competitive + pricing are where launch/defense
# decisions are won or lost, so they're critical by default; the rest tier
# down. Situation-specific tuning is a later loop.
DEFAULT_PRIORITY: dict[str, str] = {
    "disease_and_patient":    "medium",
    "clinical_profile":       "high",
    "competitive":            "critical",
    "pricing_and_access":     "critical",
    "commercial_operational": "medium",
    "hcp_and_patient":        "medium",
    "pipeline_and_macro":     "high",
    "wargame_specific":       "high",
}

# Predicate → domain routing. Exact predicate first, then prefix fallback.
# Unknown predicates land in wargame_specific (the catch-all strategic bucket)
# so nothing is silently dropped.
_PREDICATE_DOMAIN: dict[str, str] = {
    "wac_usd_monthly":      "pricing_and_access",
    "pricing_intent":       "pricing_and_access",
    "net_price":            "pricing_and_access",
    "trial_result":         "clinical_profile",
    "efficacy_outcome":     "clinical_profile",
    "safety_signal":        "clinical_profile",
    "adverse_event":        "clinical_profile",
    "fda_approval_date":    "pipeline_and_macro",
    "regulatory_approval":  "pipeline_and_macro",
    "regulatory_setback":   "pipeline_and_macro",
    "patent_event":         "pipeline_and_macro",
    "supply_disruption":    "pipeline_and_macro",
    "ma_deal":              "competitive",
    "market_share":         "competitive",
    "competitor_launch":    "competitive",
    "prevalence":           "disease_and_patient",
    "epidemiology":         "disease_and_patient",
    "revenue":              "commercial_operational",
    "sales_guidance":       "commercial_operational",
    "prescriber_trend":     "hcp_and_patient",
}

# Prefix routing for predicate families (checked after exact match).
_PREDICATE_PREFIX_DOMAIN: tuple[tuple[str, str], ...] = (
    ("price", "pricing_and_access"),
    ("payer", "pricing_and_access"),
    ("access", "pricing_and_access"),
    ("trial", "clinical_profile"),
    ("efficacy", "clinical_profile"),
    ("safety", "clinical_profile"),
    ("adverse", "clinical_profile"),
    ("regulat", "pipeline_and_macro"),
    ("approval", "pipeline_and_macro"),
    ("patent", "pipeline_and_macro"),
    ("pipeline", "pipeline_and_macro"),
    ("supply", "pipeline_and_macro"),
    ("competitor", "competitive"),
    ("market", "competitive"),
    ("deal", "competitive"),
    ("prevalence", "disease_and_patient"),
    ("epidem", "disease_and_patient"),
    ("patient", "disease_and_patient"),
    ("revenue", "commercial_operational"),
    ("sales", "commercial_operational"),
    ("guidance", "commercial_operational"),
    ("prescriber", "hcp_and_patient"),
    ("hcp", "hcp_and_patient"),
)

_FALLBACK_DOMAIN = "wargame_specific"


def route_predicate_to_domain(predicate: Optional[str]) -> str:
    """Map a fact predicate to one of the 8 ZS domains. Total function —
    unknown predicates fall back to wargame_specific (never dropped)."""
    if not predicate:
        return _FALLBACK_DOMAIN
    p = predicate.strip().lower()
    if p in _PREDICATE_DOMAIN:
        return _PREDICATE_DOMAIN[p]
    for prefix, domain in _PREDICATE_PREFIX_DOMAIN:
        if p.startswith(prefix):
            return domain
    return _FALLBACK_DOMAIN


@dataclass
class DossierFact:
    id: str
    claim: str
    fact_class: str          # one of VALID_FACT_CLASSES
    source_label: str

    def to_dict(self) -> dict:
        # camelCase to match the frontend Fact interface exactly.
        return {
            "id": self.id,
            "claim": self.claim,
            "factClass": self.fact_class,
            "sourceLabel": self.source_label,
        }


@dataclass
class DomainView:
    domain: str              # one of DOSSIER_DOMAINS
    priority: str            # critical | high | medium
    state: str               # complete | in_progress | gap
    facts: list[DossierFact] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "priority": self.priority,
            "state": self.state,
            "facts": [f.to_dict() for f in self.facts],
        }


@dataclass
class DossierSnapshot:
    engagement_id: str
    focal_asset: str
    domains: list[DomainView]
    coverage_score: float
    fact_count: int
    id: Optional[str] = None
    version: Optional[int] = None
    assembled_by: str = "system"
    assembled_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "focal_asset": self.focal_asset,
            "version": self.version,
            "coverage_score": round(self.coverage_score, 3),
            "fact_count": self.fact_count,
            "domains": [d.to_dict() for d in self.domains],
            "assembled_by": self.assembled_by,
            "assembled_at": self.assembled_at.isoformat()
                if isinstance(self.assembled_at, datetime) else self.assembled_at,
        }

    def gaps(self) -> list[dict]:
        """Domains with no usable facts — the collection priorities that feed
        the sense layer and the engagement's 'gaps' stage."""
        return [
            {"domain": d.domain, "priority": d.priority}
            for d in self.domains
            if d.state == "gap"
        ]


# ── Rendering helpers (fact dict → human-readable) ─────────────────


def _humanize(predicate: str) -> str:
    return predicate.replace("_", " ").strip().capitalize()


def _render_value(object_value: Any) -> str:
    """Compact, human-readable rendering of a fact's object_value JSONB."""
    if object_value is None:
        return ""
    if isinstance(object_value, str):
        return object_value
    if isinstance(object_value, (int, float, bool)):
        return str(object_value)
    if isinstance(object_value, dict):
        # Prefer the conventional single-value keys.
        for key in ("value", "text", "summary", "amount", "usd", "date"):
            if key in object_value:
                return str(object_value[key])
        try:
            return json.dumps(object_value, separators=(",", ":"))[:160]
        except (TypeError, ValueError):
            return str(object_value)[:160]
    return str(object_value)[:160]


def _coerce_fact_class(value: Any) -> str:
    if isinstance(value, str) and value in VALID_FACT_CLASSES:
        return value
    return "signal"  # sensible default for un-classed observed facts


def _fact_to_dossier_fact(fact: dict) -> DossierFact:
    predicate = fact.get("predicate") or ""
    claim_value = _render_value(fact.get("object_value"))
    claim = f"{_humanize(predicate)}: {claim_value}".strip().rstrip(":").strip() \
        if claim_value else _humanize(predicate)
    cls = _coerce_fact_class(fact.get("fact_class"))
    created_by = fact.get("created_by") or "system"
    conf = fact.get("confidence")
    try:
        conf_str = f" · conf {float(conf):.0%}" if conf is not None else ""
    except (TypeError, ValueError):
        conf_str = ""
    source_label = f"{created_by}{conf_str}"
    return DossierFact(
        id=str(fact.get("id") or ""),
        claim=claim,
        fact_class=cls,
        source_label=source_label,
    )


# ── Pure assembly (no DB) ──────────────────────────────────────────


def _domain_state(facts: list[DossierFact]) -> str:
    """complete = ≥3 facts with at least one grounded (reference/corporate)
    class; gap = nothing; otherwise in_progress."""
    n = len(facts)
    if n == 0:
        return "gap"
    grounded = any(f.fact_class in ("reference", "corporate") for f in facts)
    if n >= 3 and grounded:
        return "complete"
    return "in_progress"


def build_domains(facts: list[dict]) -> tuple[list[DomainView], float, int]:
    """Pure: route raw fact dicts into the 8 domains, compute per-domain state
    and the overall coverage score. No DB, no I/O — the testable core."""
    by_domain: dict[str, list[DossierFact]] = {d: [] for d in DOSSIER_DOMAINS}
    for fact in facts:
        domain = route_predicate_to_domain(fact.get("predicate"))
        by_domain[domain].append(_fact_to_dossier_fact(fact))

    domains: list[DomainView] = []
    for d in DOSSIER_DOMAINS:
        dfacts = by_domain[d]
        domains.append(DomainView(
            domain=d,
            priority=DEFAULT_PRIORITY[d],
            state=_domain_state(dfacts),
            facts=dfacts,
        ))

    covered = sum(1 for dv in domains if dv.state != "gap")
    coverage_score = covered / len(DOSSIER_DOMAINS)
    fact_count = sum(len(by_domain[d]) for d in DOSSIER_DOMAINS)
    return domains, coverage_score, fact_count


def parse_asset_ref(asset: str) -> tuple[str, str]:
    """'drug:wegovy' → ('drug', 'wegovy'). A bare value → ('drug', value)."""
    if ":" in asset:
        kind, _, ident = asset.partition(":")
        return (kind.strip() or "drug", ident.strip())
    return ("drug", asset.strip())


def _looks_like_uuid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4


# Entity-type → (table, name column) for slug→canonical-id resolution. Mirrors
# services/dossier.py:_TYPE_TO_TABLE; kept local to avoid a circular import.
_RESOLVE_TABLE: dict[str, tuple[str, str]] = {
    "drug":             ("drugs", "generic_name"),
    "company":          ("companies", "name"),
    "mechanism":        ("mechanisms_of_action", "name"),
    "trial":            ("clinical_trials", "official_title"),
    "therapeutic_area": ("therapeutic_areas", "name"),
}


def resolve_asset_to_subject(db, asset: str) -> tuple[str, str]:
    """Resolve an engagement asset ref ('drug:wegovy') to the (subject_type,
    canonical_id) the facts ledger is keyed by.

    The facts ledger stores drug subjects by the drugs.id UUID (A1 finding:
    market_events.drug_id → facts.subject_entity_id), so a raw slug never
    matches. Resolve the slug to the canonical id first:
      1. already a UUID → use as-is
      2. exact name match (drugs: generic_name OR brand_name; others: name)
      3. entity_aliases exact match
      4. unresolved → fall back to the raw slug (caller still gets a valid,
         if empty, dossier — graceful degradation, never a crash)
    """
    subject_type, ident = parse_asset_ref(asset)
    if not ident:
        return (subject_type, ident)
    if _looks_like_uuid(ident):
        return (subject_type, ident)

    table_info = _RESOLVE_TABLE.get(subject_type)
    if table_info is None:
        return (subject_type, ident)
    table, name_col = table_info

    # Exact name match. Drugs also match brand_name (the demo case: 'wegovy').
    try:
        if subject_type == "drug":
            row = db.fetch_one(
                "SELECT id::text AS id FROM drugs "
                "WHERE LOWER(generic_name) = LOWER(%s) "
                "   OR LOWER(brand_name)  = LOWER(%s) LIMIT 1",
                [ident, ident],
            )
        else:
            row = db.fetch_one(
                f"SELECT id::text AS id FROM {table} "
                f"WHERE LOWER({name_col}) = LOWER(%s) LIMIT 1",
                [ident],
            )
        if row and row.get("id"):
            return (subject_type, str(row["id"]))
    except Exception:
        logger.exception("resolve_asset_to_subject: name lookup failed for %s", asset)

    # entity_aliases fallback (alias_text → resolved entity id of this type).
    try:
        arow = db.fetch_one(
            "SELECT entity_id::text AS id FROM entity_aliases "
            "WHERE LOWER(alias_text) = LOWER(%s) AND entity_type = %s LIMIT 1",
            [ident, subject_type],
        )
        if arow and arow.get("id"):
            return (subject_type, str(arow["id"]))
    except Exception:
        logger.debug("resolve_asset_to_subject: alias lookup failed", exc_info=True)

    # Unresolved — return the raw slug. Dossier will be empty but valid.
    logger.info("resolve_asset_to_subject: unresolved asset %r (using raw slug)", asset)
    return (subject_type, ident)


# ── DB-backed orchestration ────────────────────────────────────────


def assemble_dossier(
    db,
    engagement_id: str,
    *,
    assembled_by: str = "system",
    as_of: Optional[datetime] = None,
) -> DossierSnapshot:
    """Assemble (but do NOT persist) an 8-domain dossier for an engagement,
    sourced from the facts ledger AS-OF `as_of` (default now). Raises
    EngagementNotFound if the engagement is missing."""
    from services.engagement import get_engagement
    from services.facts_ledger import facts_as_of

    engagement = get_engagement(db, engagement_id)
    if engagement is None:
        raise EngagementNotFound(engagement_id)

    # Resolve the asset slug to the canonical id the facts ledger is keyed by
    # (B2/PB-E01). The raw slug never matched, so dossiers were always empty.
    subject_type, subject_id = resolve_asset_to_subject(db, engagement.asset)
    try:
        facts = facts_as_of(db, subject_type, subject_id, as_of=as_of)
    except Exception:
        logger.exception("facts_as_of failed for %s:%s", subject_type, subject_id)
        facts = []

    domains, coverage_score, fact_count = build_domains(facts)
    return DossierSnapshot(
        engagement_id=str(engagement_id),
        focal_asset=engagement.asset,
        domains=domains,
        coverage_score=coverage_score,
        fact_count=fact_count,
        assembled_by=assembled_by,
    )


_NEXT_VERSION_SQL = """
    SELECT COALESCE(MAX(version), 0) AS v
      FROM dossier_snapshots
     WHERE engagement_id = %s
"""

_INSERT_SNAPSHOT_SQL = """
    INSERT INTO dossier_snapshots (
        engagement_id, focal_asset, version, domains,
        coverage_score, fact_count, assembled_by, tenant_scope
    ) VALUES (
        %(engagement_id)s, %(focal_asset)s, %(version)s, %(domains)s::jsonb,
        %(coverage_score)s, %(fact_count)s, %(assembled_by)s, %(tenant_scope)s
    )
    RETURNING id, assembled_at
"""

_SUPERSEDE_SQL = """
    UPDATE dossier_snapshots
       SET superseded_by = %s
     WHERE engagement_id = %s
       AND id <> %s
       AND superseded_by IS NULL
"""

_SELECT_LATEST_SQL = """
    SELECT id, engagement_id, focal_asset, version, domains,
           coverage_score, fact_count, assembled_by, assembled_at
      FROM dossier_snapshots
     WHERE engagement_id = %s
       AND superseded_by IS NULL
     ORDER BY version DESC
     LIMIT 1
"""

_LIST_VERSIONS_SQL = """
    SELECT id, version, coverage_score, fact_count, assembled_by, assembled_at
      FROM dossier_snapshots
     WHERE engagement_id = %s
     ORDER BY version DESC
"""


def persist_snapshot(db, snapshot: DossierSnapshot) -> str:
    """Write a snapshot as the next version for its engagement and supersede
    the prior head. Mutates `snapshot` (id, version, assembled_at) and returns
    the new id."""
    row = db.fetch_one(_NEXT_VERSION_SQL, [snapshot.engagement_id])
    next_version = int((row or {}).get("v", 0)) + 1

    params = {
        "engagement_id": snapshot.engagement_id,
        "focal_asset": snapshot.focal_asset,
        "version": next_version,
        "domains": json.dumps([d.to_dict() for d in snapshot.domains]),
        "coverage_score": round(snapshot.coverage_score, 4),
        "fact_count": snapshot.fact_count,
        "assembled_by": snapshot.assembled_by,
        "tenant_scope": None,
    }
    res = db.fetch_one(_INSERT_SNAPSHOT_SQL, params)
    new_id = str(res["id"]) if res and res.get("id") else None
    snapshot.id = new_id
    snapshot.version = next_version
    if res and res.get("assembled_at") is not None:
        snapshot.assembled_at = res["assembled_at"]

    # Point the prior head(s) at the new version (append-only supersession).
    if new_id is not None:
        try:
            db.execute(_SUPERSEDE_SQL, [new_id, snapshot.engagement_id, new_id])
        except Exception:
            logger.exception("supersede prior dossier snapshot failed")
    return new_id or ""


def assemble_and_persist(
    db,
    engagement_id: str,
    *,
    assembled_by: str = "system",
    as_of: Optional[datetime] = None,
) -> DossierSnapshot:
    """Assemble + persist in one shot. Returns the persisted snapshot."""
    snapshot = assemble_dossier(
        db, engagement_id, assembled_by=assembled_by, as_of=as_of,
    )
    persist_snapshot(db, snapshot)
    return snapshot


def _row_to_snapshot(row: dict) -> DossierSnapshot:
    raw_domains = row.get("domains")
    if isinstance(raw_domains, str):
        try:
            raw_domains = json.loads(raw_domains)
        except (TypeError, ValueError):
            raw_domains = []
    domains: list[DomainView] = []
    for d in (raw_domains or []):
        facts = [
            DossierFact(
                id=str(f.get("id", "")),
                claim=f.get("claim", ""),
                fact_class=_coerce_fact_class(f.get("factClass")),
                source_label=f.get("sourceLabel", ""),
            )
            for f in (d.get("facts") or [])
        ]
        domains.append(DomainView(
            domain=d.get("domain", ""),
            priority=d.get("priority", "medium"),
            state=d.get("state", "gap"),
            facts=facts,
        ))
    return DossierSnapshot(
        id=str(row["id"]) if row.get("id") is not None else None,
        engagement_id=str(row["engagement_id"]),
        focal_asset=row.get("focal_asset", ""),
        version=row.get("version"),
        domains=domains,
        coverage_score=float(row.get("coverage_score") or 0),
        fact_count=int(row.get("fact_count") or 0),
        assembled_by=row.get("assembled_by", "system"),
        assembled_at=row.get("assembled_at"),
    )


def get_latest_snapshot(db, engagement_id: str) -> Optional[DossierSnapshot]:
    try:
        row = db.fetch_one(_SELECT_LATEST_SQL, [engagement_id])
    except Exception:
        logger.exception("get_latest_snapshot failed for %s", engagement_id)
        return None
    if not row:
        return None
    return _row_to_snapshot(row)


def list_snapshot_versions(db, engagement_id: str) -> list[dict]:
    """Lightweight version index for the knowledge base (no domain payloads)."""
    try:
        rows = db.fetch_all(_LIST_VERSIONS_SQL, [engagement_id])
    except Exception:
        logger.exception("list_snapshot_versions failed for %s", engagement_id)
        return []
    out = []
    for r in rows or []:
        assembled_at = r.get("assembled_at")
        out.append({
            "id": str(r["id"]) if r.get("id") is not None else None,
            "version": r.get("version"),
            "coverage_score": round(float(r.get("coverage_score") or 0), 3),
            "fact_count": int(r.get("fact_count") or 0),
            "assembled_by": r.get("assembled_by", "system"),
            "assembled_at": assembled_at.isoformat()
                if isinstance(assembled_at, datetime) else assembled_at,
        })
    return out
