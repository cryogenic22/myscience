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
import re
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

# H04/H05: per-domain readiness weighting + gap framing. Priority weights roll
# domain readiness into one engagement-level number (benchmark's "readiness 87%").
_PRIORITY_WEIGHT: dict[str, float] = {"critical": 3.0, "high": 2.0, "medium": 1.0}

# Human label per domain — used in gap descriptions.
_DOMAIN_LABEL: dict[str, str] = {
    "disease_and_patient":    "disease & patient landscape",
    "clinical_profile":       "clinical profile of the focal asset",
    "competitive":            "competitive landscape",
    "pricing_and_access":     "payer & access",
    "commercial_operational": "commercial & operational",
    "hcp_and_patient":        "HCP & patient adoption",
    "pipeline_and_macro":     "pipeline & macro / regulatory",
    "wargame_specific":       "wargame / strategic design",
}

# How a thin/empty domain gets filled — points the sense layer at the right
# collection. Honest and domain-appropriate (no invented primary-research prose).
_DOMAIN_FILL_METHOD: dict[str, str] = {
    "disease_and_patient":    "Pull epidemiology + patient-flow facts (PubMed, KFF, IQVIA channel data).",
    "clinical_profile":       "Ingest trial readouts + label data (ClinicalTrials.gov, FDA, PubMed) for the focal asset.",
    "competitive":            "Expand the entity graph around the asset (shared mechanism / TA) + competitive_landscape metrics.",
    "pricing_and_access":     "Triangulate payer/pricing sources (NADAC, ICER, formulary feeds) — net price needs triangulation.",
    "commercial_operational": "Ingest corporate financials + sales guidance (SEC filings, earnings).",
    "hcp_and_patient":        "Add prescriber-trend + KOL signals (IQVIA Xponent, investigator links, internal panels).",
    "pipeline_and_macro":     "Track regulatory + pipeline events (FDA, ClinicalTrials.gov, patents).",
    "wargame_specific":       "Capture the engagement's strategic questions + scenario triggers from the brief.",
}


def _importance_from_priority(priority: str) -> str:
    """Gap importance (benchmark uses high/medium): critical+high domains are
    high-importance gaps; everything else is medium."""
    return "high" if priority in ("critical", "high") else "medium"


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
    # DR-1/DR-3/DR-4 fact-emitter predicates (lifted from entity tables).
    "clinical_trial":       "clinical_profile",
    "adverse_event_report": "clinical_profile",
    "label_indication":     "clinical_profile",
    # DR-6 mechanism/target fact-emitter predicates (ChEMBL/MeSH-derived).
    "mechanism_of_action":  "clinical_profile",
    "target_activity":      "clinical_profile",
    # DR-7 literature fact-emitter predicates (PubMed-derived).
    "key_publication":      "clinical_profile",
    "disease_evidence":     "disease_and_patient",
    "fda_approval_date":    "pipeline_and_macro",
    "regulatory_approval":  "pipeline_and_macro",
    "regulatory_setback":   "pipeline_and_macro",
    "patent_event":         "pipeline_and_macro",
    "supply_disruption":    "pipeline_and_macro",
    "ma_deal":              "competitive",
    "market_share":         "competitive",
    "competitor_launch":    "competitive",
    # PB-H07: the generic fallback predicate for uncategorized events (recalls,
    # shortages, misc news) is "market_event" — it must NOT hit the "market"
    # prefix rule below (which would dump every generic event into the
    # competitive domain: 505 FDA-recall facts buried metformin's real rivals).
    # Route it to the strategic catch-all instead. Exact match wins over prefix.
    "market_event":         "wargame_specific",
    "prevalence":           "disease_and_patient",
    "epidemiology":         "disease_and_patient",
    "revenue":              "commercial_operational",
    "sales_guidance":       "commercial_operational",
    # L7 / Tier 2: product-level net sales from uploaded earnings docs (and,
    # later, warehouse/syndicated connectors). Starts with "product", so it
    # needs an exact entry — the "sales" prefix rule below would miss it.
    "product_sales":        "commercial_operational",
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
    ("mechanism", "clinical_profile"),
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

# B3: signals (recent_moves) carry a KBQ tag, a DIFFERENT taxonomy from fact
# predicates (the signals table's kbq_tags vocabulary). Map them explicitly so
# a pricing/clinical/financial signal lands in the right domain instead of all
# falling to wargame_specific.
_KBQ_TAG_DOMAIN: dict[str, str] = {
    "pricing_access":  "pricing_and_access",
    "pricing":         "pricing_and_access",
    "access":          "pricing_and_access",
    "clinical":        "clinical_profile",
    "safety":          "clinical_profile",
    "regulatory":      "pipeline_and_macro",
    "product":         "pipeline_and_macro",
    "m_and_a":         "competitive",
    "competitive":     "competitive",
    "financial":       "commercial_operational",
    "governance":      "commercial_operational",
    "strategic":       "wargame_specific",
}


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


def route_kbq_tag_to_domain(tag: Optional[str]) -> str:
    """Map a signal's KBQ tag to a ZS domain (B3). Falls back through the
    predicate router, then to wargame_specific."""
    if not tag:
        return _FALLBACK_DOMAIN
    t = tag.strip().lower()
    if t in _KBQ_TAG_DOMAIN:
        return _KBQ_TAG_DOMAIN[t]
    return route_predicate_to_domain(t)


@dataclass
class DossierFact:
    id: str
    claim: str
    fact_class: str          # one of VALID_FACT_CLASSES
    source_label: str
    source_url: Optional[str] = None   # PB-E05: drill-through to the source

    def to_dict(self) -> dict:
        # camelCase to match the frontend Fact interface exactly.
        d = {
            "id": self.id,
            "claim": self.claim,
            "factClass": self.fact_class,
            "sourceLabel": self.source_label,
        }
        if self.source_url:
            d["sourceUrl"] = self.source_url
        return d


@dataclass
class DomainView:
    domain: str              # one of DOSSIER_DOMAINS
    priority: str            # critical | high | medium
    state: str               # complete | in_progress | gap
    facts: list[DossierFact] = field(default_factory=list)
    readiness: float = 0.0   # H05: 0..1 per-domain evidence readiness

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "priority": self.priority,
            "state": self.state,
            "readiness": round(self.readiness, 2),
            "facts": [f.to_dict() for f in self.facts],
        }


@dataclass
class GapView:
    """H04: an actionable collection gap — what's missing, how to fill it,
    and how much it matters. Drives the engagement's gaps stage and the
    sense layer's collection priorities (mirrors the benchmark's gap shape)."""
    domain: str
    priority: str
    importance: str          # high | medium (derived from priority)
    text: str                # human-readable: what is missing
    method: str              # how to fill it (domain-appropriate collection)
    thin: bool = False       # True = some evidence but below threshold

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "priority": self.priority,
            "importance": self.importance,
            "text": self.text,
            "method": self.method,
            "thin": self.thin,
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
    # L7: how the focal asset resolved (id|exact|alias|normalized|fuzzy|unresolved).
    # 'unresolved' means the dossier is empty because the asset wasn't found, NOT
    # because the entity has no data — the UI surfaces these very differently.
    resolution: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.resolution != "unresolved"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "engagement_id": self.engagement_id,
            "focal_asset": self.focal_asset,
            "version": self.version,
            "coverage_score": round(self.coverage_score, 3),
            "readiness": overall_readiness(self.domains),
            "fact_count": self.fact_count,
            "domains": [d.to_dict() for d in self.domains],
            "assembled_by": self.assembled_by,
            "assembled_at": self.assembled_at.isoformat()
                if isinstance(self.assembled_at, datetime) else self.assembled_at,
            "resolution": self.resolution,
            "resolved": self.resolved,
        }

    def gaps(self, include_thin: bool = False) -> list[dict]:
        """Actionable collection gaps (H04) — what's missing, how to fill it,
        how much it matters. Empty (`gap`-state) domains are always gaps; with
        `include_thin=True`, under-covered (`in_progress`) domains surface too.
        Each entry carries text + method + importance (the benchmark's gap
        shape). Default `include_thin=False` preserves the original empty-only
        contract for existing callers."""
        out: list[dict] = []
        for d in self.domains:
            if d.state == "gap":
                out.append(self._gap_view(d, thin=False).to_dict())
            elif include_thin and d.state == "in_progress":
                out.append(self._gap_view(d, thin=True).to_dict())
        return out

    def source_coverage(self) -> list[dict]:
        """UX07: per-source contribution to THIS engagement's dossier — which
        sources fed it, how many facts each, which domains they touch, and the
        confidence-class mix. Derived from the snapshot's facts (the source_label
        prefix before '·' is the source); engagement-scoped consumption, no extra
        query. Sorted by fact_count desc."""
        agg: dict[str, dict] = {}
        for d in self.domains:
            label = _DOMAIN_LABEL.get(d.domain, d.domain.replace("_", " "))
            for f in d.facts:
                src = (f.source_label or "—").split("·")[0].strip() or "—"
                e = agg.setdefault(src, {
                    "source": src, "fact_count": 0,
                    "domains": set(), "classes": {},
                })
                e["fact_count"] += 1
                e["domains"].add(label)
                e["classes"][f.fact_class] = e["classes"].get(f.fact_class, 0) + 1
        out = []
        for e in agg.values():
            out.append({
                "source": e["source"],
                "fact_count": e["fact_count"],
                "domains": sorted(e["domains"]),
                "classes": e["classes"],
            })
        out.sort(key=lambda x: x["fact_count"], reverse=True)
        return out

    @staticmethod
    def _gap_view(d: DomainView, *, thin: bool) -> GapView:
        label = _DOMAIN_LABEL.get(d.domain, d.domain.replace("_", " "))
        if thin:
            n = len(d.facts)
            text = f"Thin coverage for {label}: only {n} fact(s) so far, below the bar for a confident view."
        else:
            text = f"No evidence collected yet for {label}."
        return GapView(
            domain=d.domain,
            priority=d.priority,
            importance=_importance_from_priority(d.priority),
            text=text,
            method=_DOMAIN_FILL_METHOD.get(d.domain, "Collect domain-relevant facts via the sense layer."),
            thin=thin,
        )


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
        # Prefer the conventional single-value keys. `description` is included
        # because market_event facts carry their human text there — without it
        # they rendered as raw JSON ("{\"event_id\":...}") which then leaked
        # into scenario names + narrative. Skip None/empty so we fall through
        # to the next key rather than printing "None".
        for key in ("value", "text", "summary", "description", "amount", "usd", "date"):
            if object_value.get(key) not in (None, ""):
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
    # PB-E05: surface the source URL (market_event facts carry it in
    # object_value) so the dossier UI can drill through to the source record.
    ov = fact.get("object_value")
    source_url = ov.get("source_url") if isinstance(ov, dict) else None
    return DossierFact(
        id=str(fact.get("id") or ""),
        claim=claim,
        fact_class=cls,
        source_label=source_label,
        source_url=source_url or None,
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


def _domain_readiness(facts: list[DossierFact]) -> float:
    """H05: per-domain readiness in [0,1] — deterministic, no LLM. Combines
    breadth (fact count, capped at 6) with trust (a grounded reference/corporate
    fact present). Empty → 0.0; a single ungrounded signal → ~0.10; three
    grounded facts → ~0.70; six+ grounded → 1.0. Mirrors the benchmark's
    per-domain `ready` score so thin domains read as low-confidence."""
    n = len(facts)
    if n == 0:
        return 0.0
    count_score = min(n, 6) / 6.0
    grounded = 1.0 if any(f.fact_class in ("reference", "corporate") for f in facts) else 0.0
    return round(0.6 * count_score + 0.4 * grounded, 2)


def overall_readiness(domains: list[DomainView]) -> float:
    """Priority-weighted mean of per-domain readiness → the engagement-level
    readiness number (benchmark shows e.g. 87%). Critical domains count 3×,
    high 2×, medium 1×, so a strong competitive domain matters more than a
    strong wargame_specific one."""
    total_w = 0.0
    acc = 0.0
    for d in domains:
        w = _PRIORITY_WEIGHT.get(d.priority, 1.0)
        total_w += w
        acc += w * d.readiness
    return round(acc / total_w, 3) if total_w else 0.0


def _signal_to_dossier_fact(move: dict) -> DossierFact:
    """A compose_dossier recent_move (signal) → DossierFact (signal class)."""
    headline = move.get("headline") or "signal"
    kbq = move.get("kbq_tag")
    claim = f"{headline}" if not kbq else f"[{kbq}] {headline}"
    return DossierFact(
        id=str(move.get("signal_id") or ""),
        claim=claim,
        fact_class="signal",
        source_label="signal" + (f" · {move['ts'][:10]}" if move.get("ts") else ""),
        source_url=move.get("source_url") or None,    # PB-E05
    )


# Link types that mark a related entity as competitively relevant: shared
# mechanism / TA = competes for the same indication; explicit COMPETES_WITH.
_COMPETITIVE_RELATIONS = {"competes_with", "targets_mechanism", "in_therapeutic_area"}


def _related_to_dossier_fact(rel: dict) -> DossierFact:
    """B5: a compose_dossier related_entity → competitive-domain DossierFact,
    carrying the cited graph edge (relation + edge_count)."""
    rel_type = (rel.get("relation") or "linked").lower()
    name = rel.get("name") or rel.get("id") or "entity"
    rtype = rel.get("type") or "entity"
    edges = rel.get("edge_count")
    claim = f"{rtype}:{name} — {rel_type}"
    if edges:
        claim += f" ({edges} edges)"
    return DossierFact(
        id=str(rel.get("id") or ""),
        claim=claim,
        # inferred: derived from the graph, not a primary corporate/reference fact
        fact_class="inferred",
        source_label=f"entity_graph · {rel_type}",
    )


# Trial-arm markers that mean "this 'drug' row is actually a study arm, not a
# competitor". A6's _should_exclude anchors placebo to the name start (it cleans
# rows where the WHOLE name is junk); in the competitive set the marker is
# usually a suffix ("metformin placebo", "X + healthy diet"), so we also scan
# anywhere for these.
_COMPETITOR_ARM_RE = re.compile(
    r"(?:\bplacebo\b|\bsham\b|\bvehicle\b|\busual care\b|\bstandard of care\b|"
    r"\bhealthy diet\b|\blifestyle\b|\bexercise\b|treatment for|\bcomparator\b|"
    # RC4: dosing-arm descriptors that mean 'this is a study arm / formulation
    # variant of a drug, not a distinct competitor' — e.g. 'Tirzepatide Dose 1',
    # 'X high dose', 'Y QW', 'Z pen', 'once weekly'.
    r"\bdose\s*\d+\b|\b(?:low|mid|middle|high)\s+dose\b|\bdose\s+(?:low|mid|middle|high)\b|"
    r"\b(?:once\s+)?(?:weekly|daily|monthly)\b|\bq[dwm]\b|\bb?id\b|\btid\b|"
    r"\bpen\b|\bautoinjector\b|\bprefilled\b)",
    re.IGNORECASE,
)

# Noise tokens stripped to compare a competitor's BASE name against the subject's
# (RC4 self-competition: 'Tirzepatide Dose 1' must not be a competitor of
# tirzepatide). Strips dosing/formulation/arm noise + numbers.
_BASE_NOISE_RE = re.compile(
    r"\b(?:dose|arm|cohort|group|pen|injection|injectable|tablet|capsule|oral|"
    r"subcutaneous|sc|iv|qd|qw|qm|bid|tid|weekly|daily|monthly|low|mid|middle|"
    r"high|placebo|product|extended|release|er|ir|xr|sr)\b|"
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|ml|units?|iu)?",
    re.IGNORECASE,
)


def _base_drug_name(name: Optional[str]) -> str:
    """Reduce a drug/arm name to its base for self-competition comparison."""
    if not name:
        return ""
    base = _BASE_NOISE_RE.sub(" ", name.lower())
    base = re.sub(r"[^a-z ]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def _is_junk_competitor_name(name: Optional[str], subject_name: Optional[str] = None) -> bool:
    """Read-time filter for junk drug rows (placebo / dosage / trial-arm names —
    e.g. 'metformin placebo', 'Metformin 1000mg', 'Tirzepatide Dose 1') that the
    entity graph links as COMPETES_WITH neighbours and that would otherwise
    present as 'competitors'. When ``subject_name`` is given, also suppresses
    self-competition: a 'competitor' whose base name equals the subject's
    (RC4 — the dossier's own drug appearing as its rival via a dosing variant).

    Reuses the A6 cleanup patterns (scripts.clean_drug_names) PLUS a trial-arm
    scan for the competitive context — the NON-destructive, read-time complement
    to A6's write-time cleanup. Lazy import keeps the pure assembly core free of
    script-level deps."""
    if not name:
        return False
    if subject_name:
        base = _base_drug_name(name)
        if base and base == _base_drug_name(subject_name):
            return True  # self-competition (same drug, different arm/dose)
    if _COMPETITOR_ARM_RE.search(name):
        return True
    try:
        from scripts.clean_drug_names import _should_exclude, DOSAGE_PATTERN
        return bool(_should_exclude(name) or DOSAGE_PATTERN.search(name))
    except Exception:  # never let a filter failure drop a real competitor
        return False


def build_domains(
    facts: list[dict],
    signals: Optional[list[dict]] = None,
    metric_facts: Optional[list[tuple[str, "DossierFact"]]] = None,
    related: Optional[list[dict]] = None,
    subject_name: Optional[str] = None,
) -> tuple[list[DomainView], float, int]:
    """Pure: route ledger facts + (B3) compose_dossier signals + (B4) metric
    facts + (B5) competitively-relevant related entities into the 8 domains,
    compute per-domain state and overall coverage. No DB, no I/O — the testable
    core. Signals route by kbq_tag; metric_facts arrive pre-routed; related are
    pre-filtered competitive entities routed to the competitive domain."""
    by_domain: dict[str, list[DossierFact]] = {d: [] for d in DOSSIER_DOMAINS}
    for fact in facts:
        domain = route_predicate_to_domain(fact.get("predicate"))
        by_domain[domain].append(_fact_to_dossier_fact(fact))

    for move in (signals or []):
        domain = route_kbq_tag_to_domain(move.get("kbq_tag"))
        by_domain[domain].append(_signal_to_dossier_fact(move))

    for domain, dfact in (metric_facts or []):
        if domain in by_domain:
            by_domain[domain].append(dfact)

    for rel in (related or []):
        # Skip junk drug rows (placebo/dosage/trial-arm) masquerading as
        # competitors — reuses the A6 patterns, read-time (PB-H07).
        if (rel.get("type") == "drug") and _is_junk_competitor_name(rel.get("name"), subject_name):
            continue
        by_domain["competitive"].append(_related_to_dossier_fact(rel))

    domains: list[DomainView] = []
    for d in DOSSIER_DOMAINS:
        dfacts = by_domain[d]
        domains.append(DomainView(
            domain=d,
            priority=DEFAULT_PRIORITY[d],
            state=_domain_state(dfacts),
            facts=dfacts,
            readiness=_domain_readiness(dfacts),
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


@dataclass(frozen=True)
class ResolvedAsset:
    """The outcome of resolving an asset ref, with HOW it matched so callers can
    surface an honest 'unresolved asset' state instead of a silent-empty dossier."""

    subject_type: str
    subject_id: str
    matched_via: str  # id | exact | alias | normalized | fuzzy | unresolved

    @property
    def resolved(self) -> bool:
        return self.matched_via != "unresolved"


# Fuzzy (pg_trgm) tables: (table, name_col, brand_col|None). Only drug/company —
# the entities a user types by hand and mistypes; trials/MoAs are picked from UI.
_FUZZY_TABLE: dict[str, tuple[str, str, Optional[str]]] = {
    "drug": ("drugs", "generic_name", "brand_name"),
    "company": ("companies", "name", None),
}
# trigram similarity floor for a fuzzy match. 0.45 catches single-char typos
# (semaglutid→semaglutide ≈ 0.77, empagliflozn→empagliflozin ≈ 0.69) while
# staying well above unrelated-name noise.
_FUZZY_THRESHOLD = 0.45


def _exact_lookup(db, subject_type: str, ident: str) -> Optional[str]:
    """Exact name match → canonical id, or None. Drugs also match brand_name and
    rank duplicate rows by data richness (RC1) so the evidence-owning row wins."""
    table_info = _RESOLVE_TABLE.get(subject_type)
    if table_info is None:
        return None
    table, name_col = table_info
    try:
        if subject_type == "drug":
            row = db.fetch_one(
                "SELECT d.id::text AS id, "
                "  (SELECT count(*) FROM facts f "
                "     WHERE f.subject_entity_type = 'drug' "
                "       AND f.subject_entity_id = d.id::text "
                "       AND f.superseded_by IS NULL) "
                "  + (SELECT count(*) FROM clinical_trials ct "
                "       WHERE ct.drug_id = d.id) AS richness "
                "FROM drugs d "
                "WHERE (LOWER(d.generic_name) = LOWER(%s) "
                "    OR LOWER(d.brand_name)  = LOWER(%s)) "
                "  AND d.record_status IS DISTINCT FROM 'merged' "
                "  AND d.record_status IS DISTINCT FROM 'superseded' "
                "ORDER BY richness DESC, d.id "
                "LIMIT 1",
                [ident, ident],
            )
        else:
            row = db.fetch_one(
                f"SELECT id::text AS id FROM {table} "
                f"WHERE LOWER({name_col}) = LOWER(%s) LIMIT 1",
                [ident],
            )
        if row and row.get("id"):
            return str(row["id"])
    except Exception:
        logger.exception("resolve: exact lookup failed for %s:%s", subject_type, ident)
    return None


def _alias_lookup(db, subject_type: str, ident: str) -> Optional[str]:
    """entity_aliases exact match → canonical id, or None."""
    try:
        arow = db.fetch_one(
            "SELECT entity_id::text AS id FROM entity_aliases "
            "WHERE LOWER(alias_text) = LOWER(%s) AND entity_type = %s LIMIT 1",
            [ident, subject_type],
        )
        if arow and arow.get("id"):
            return str(arow["id"])
    except Exception:
        logger.debug("resolve: alias lookup failed", exc_info=True)
    return None


def _normalize_ident(subject_type: str, ident: str) -> Optional[str]:
    """Clean a noisy mention ('Ozempic (semaglutide)', 'tirzepatide injection',
    'Wegovy 2.4mg') to its core name via the pharma mention normalizers. Returns
    the normalized form only if it actually differs from the input."""
    try:
        if subject_type == "drug":
            from domain.pharma.mention_normalizer import normalize_drug_mention
            n = normalize_drug_mention(ident)
        elif subject_type == "company":
            from domain.pharma.mention_normalizer import normalize_company_mention
            n = normalize_company_mention(ident)
        else:
            return None
    except Exception:
        logger.debug("resolve: mention normalize failed", exc_info=True)
        return None
    n = (n or "").strip()
    if not n or n.lower() == ident.lower():
        return None
    return n


def _fuzzy_lookup(db, subject_type: str, ident: str) -> Optional[str]:
    """Trigram-similarity match for typos/variants, gated by _FUZZY_THRESHOLD and
    (for drugs) ranked by richness. Degrades to None if pg_trgm is unavailable."""
    info = _FUZZY_TABLE.get(subject_type)
    if info is None or not ident:
        return None
    try:
        if subject_type == "drug":
            row = db.fetch_one(
                "SELECT d.id::text AS id, "
                "  GREATEST(similarity(LOWER(d.generic_name), LOWER(%s)), "
                "           similarity(LOWER(COALESCE(d.brand_name, '')), LOWER(%s))) AS sim, "
                "  (SELECT count(*) FROM facts f "
                "     WHERE f.subject_entity_type = 'drug' "
                "       AND f.subject_entity_id = d.id::text "
                "       AND f.superseded_by IS NULL) "
                "  + (SELECT count(*) FROM clinical_trials ct "
                "       WHERE ct.drug_id = d.id) AS richness "
                "FROM drugs d "
                "WHERE d.record_status IS DISTINCT FROM 'merged' "
                "  AND d.record_status IS DISTINCT FROM 'superseded' "
                "  AND (similarity(LOWER(d.generic_name), LOWER(%s)) >= %s "
                "    OR similarity(LOWER(COALESCE(d.brand_name, '')), LOWER(%s)) >= %s) "
                "ORDER BY sim DESC, richness DESC, d.id "
                "LIMIT 1",
                [ident, ident, ident, _FUZZY_THRESHOLD, ident, _FUZZY_THRESHOLD],
            )
        else:
            row = db.fetch_one(
                "SELECT id::text AS id, similarity(LOWER(name), LOWER(%s)) AS sim "
                "FROM companies "
                "WHERE similarity(LOWER(name), LOWER(%s)) >= %s "
                "ORDER BY sim DESC, id LIMIT 1",
                [ident, ident, _FUZZY_THRESHOLD],
            )
        if row and row.get("id"):
            return str(row["id"])
    except Exception:
        logger.debug("resolve: fuzzy lookup unavailable for %s", subject_type, exc_info=True)
    return None


def resolve_asset(db, asset: str) -> ResolvedAsset:
    """Resolve an asset ref ('drug:wegovy') to the canonical id the facts ledger
    is keyed by, recording HOW it matched. Cascade (cheap → expensive):

      1. already a UUID                                   → matched_via='id'
      2. exact name (drugs: generic_name OR brand_name,
         richness-ranked; others: name)                  → 'exact'
      3. entity_aliases exact                             → 'alias'
      4. normalized mention retry (2+3 on the cleaned
         name: 'Ozempic (semaglutide)'→'ozempic')        → 'normalized'
      5. trigram fuzzy (typo/variant tolerance)           → 'fuzzy'
      6. unresolved → raw slug (valid-but-empty dossier;  → 'unresolved'
         the caller surfaces this honestly, never crashes)

    Steps 4–5 are the L7 addition: an unknown brand or a noisy/mistyped name used
    to fall straight through to a silent-empty dossier. Now they resolve, and a
    genuine miss is *flagged* (resolved=False) instead of looking like 'no data'.
    """
    subject_type, ident = parse_asset_ref(asset)
    if not ident:
        return ResolvedAsset(subject_type, ident, "unresolved")
    if _looks_like_uuid(ident):
        return ResolvedAsset(subject_type, ident, "id")

    hid = _exact_lookup(db, subject_type, ident)
    if hid:
        return ResolvedAsset(subject_type, hid, "exact")

    hid = _alias_lookup(db, subject_type, ident)
    if hid:
        return ResolvedAsset(subject_type, hid, "alias")

    norm = _normalize_ident(subject_type, ident)
    if norm:
        hid = _exact_lookup(db, subject_type, norm) or _alias_lookup(db, subject_type, norm)
        if hid:
            return ResolvedAsset(subject_type, hid, "normalized")

    for cand in [ident] + ([norm] if norm else []):
        hid = _fuzzy_lookup(db, subject_type, cand)
        if hid:
            return ResolvedAsset(subject_type, hid, "fuzzy")

    logger.info("resolve_asset: unresolved asset %r (using raw slug)", asset)
    return ResolvedAsset(subject_type, ident, "unresolved")


def resolve_asset_to_subject(db, asset: str) -> tuple[str, str]:
    """Back-compat tuple wrapper over :func:`resolve_asset` — returns just
    (subject_type, subject_id). Existing callers are unchanged."""
    r = resolve_asset(db, asset)
    return (r.subject_type, r.subject_id)


# ── DB-backed orchestration ────────────────────────────────────────


def _metric_facts(db, subject_type: str, subject_id: str) -> list[tuple[str, DossierFact]]:
    """B4/PB-E03: pull quant metrics from PharmaMetrics (materialized views)
    for a drug subject and emit them as corporate-class DossierFacts, each
    pre-routed to its ZS domain. Best-effort: any MV miss degrades to fewer
    facts, never an error. Only drugs have these metrics today."""
    if subject_type != "drug" or not subject_id:
        return []
    out: list[tuple[str, DossierFact]] = []
    try:
        from services.metrics import PharmaMetrics
        from config import config as _cfg
        pm = PharmaMetrics(db, _cfg)
    except Exception:
        logger.debug("PharmaMetrics unavailable for metric facts", exc_info=True)
        return []

    def _mk(fid: str, claim: str) -> DossierFact:
        return DossierFact(id=fid, claim=claim, fact_class="corporate",
                           source_label="PharmaMetrics · materialized view")

    # Pipeline strength → pipeline_and_macro
    try:
        rows = pm.drug_pipeline_strength(drug_id=subject_id, limit=1) or []
        if rows:
            r = rows[0]
            score = r.get("pipeline_score")
            pct = r.get("percentile_rank")
            total = r.get("total_trials")
            if score is not None:
                claim = f"Pipeline score {round(float(score), 1)}"
                if pct is not None:
                    claim += f" ({pct}th percentile)"
                if total is not None:
                    claim += f" across {total} trials"
                out.append(("pipeline_and_macro", _mk(f"metric-pipeline-{subject_id}", claim)))
    except Exception:
        logger.debug("drug_pipeline_strength metric fact failed", exc_info=True)

    # Trial success → clinical_profile
    try:
        rows = pm.trial_success_rate(drug_id=subject_id, limit=1) or []
        if rows:
            r = rows[0]
            sr = r.get("success_rate")
            if sr is not None:
                out.append(("clinical_profile",
                            _mk(f"metric-success-{subject_id}",
                                f"Trial success rate {round(float(sr) * 100)}%")))
    except Exception:
        logger.debug("trial_success_rate metric fact failed", exc_info=True)

    # Evidence density → clinical_profile
    try:
        rows = pm.evidence_density(drug_id=subject_id, limit=1) or []
        if rows:
            r = rows[0]
            total_articles = r.get("total_articles") or r.get("article_count")
            if total_articles is not None:
                out.append(("clinical_profile",
                            _mk(f"metric-evidence-{subject_id}",
                                f"{total_articles} PubMed articles (evidence density)")))
    except Exception:
        logger.debug("evidence_density metric fact failed", exc_info=True)

    return out


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

    snap = assemble_dossier_for_asset(
        db, engagement.asset, assembled_by=assembled_by, as_of=as_of)
    snap.engagement_id = str(engagement_id)
    return snap


def assemble_dossier_for_asset(
    db,
    asset: str,
    *,
    assembled_by: str = "system",
    as_of: Optional[datetime] = None,
) -> DossierSnapshot:
    """IX-3: assemble (but do NOT persist) an 8-domain dossier for ANY asset,
    independent of an engagement — the standalone 'build a dossier' light path.
    Same resolve → facts → compose → metrics → build_domains pipeline the
    engagement path uses; returns a snapshot with engagement_id=None."""
    from services.facts_ledger import facts_as_of

    # Resolve the asset slug to the canonical id the facts ledger is keyed by
    # (B2/PB-E01). The raw slug never matched, so dossiers were always empty.
    resolved = resolve_asset(db, asset)
    subject_type, subject_id = resolved.subject_type, resolved.subject_id
    try:
        facts = facts_as_of(db, subject_type, subject_id, as_of=as_of)
    except Exception:
        logger.exception("facts_as_of failed for %s:%s", subject_type, subject_id)
        facts = []

    # B3/PB-E02: compose from the EXISTING knowledge layer too, not facts-only.
    signals: list[dict] = []
    related: list[dict] = []
    try:
        from services.dossier import compose_dossier
        composed = compose_dossier(db, entity_type=subject_type, slug_or_id=subject_id)
        if composed is not None:
            signals = list(composed.recent_moves or [])
            # B5/PB-E04: competitive breadth — related entities that share a
            # mechanism / TA (or explicitly compete) are the competitive set.
            related = [
                r for r in (composed.related_entities or [])
                if (r.get("relation") or "").lower() in _COMPETITIVE_RELATIONS
            ]
    except Exception:
        logger.debug("compose_dossier merge failed; facts-only", exc_info=True)

    # B4/PB-E03: quant-backed facts from PharmaMetrics (materialized views).
    metric_facts = _metric_facts(db, subject_type, subject_id)

    # RC4: the subject's own name, to suppress self-competition in the
    # competitive domain (a dosing variant of the focal drug appearing as a rival).
    subject_name = None
    if subject_type == "drug":
        try:
            r = db.fetch_one("SELECT generic_name FROM drugs WHERE id::text = %s",
                             [str(subject_id)])
            subject_name = r.get("generic_name") if r else None
        except Exception:
            logger.debug("subject name lookup failed for %s", subject_id, exc_info=True)

    domains, coverage_score, fact_count = build_domains(
        facts, signals, metric_facts, related, subject_name=subject_name)
    return DossierSnapshot(
        engagement_id=None,
        focal_asset=asset,
        domains=domains,
        coverage_score=coverage_score,
        fact_count=fact_count,
        assembled_by=assembled_by,
        resolution=resolved.matched_via,
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
                source_url=f.get("sourceUrl") or None,
            )
            for f in (d.get("facts") or [])
        ]
        stored_readiness = d.get("readiness")
        readiness = (
            float(stored_readiness)
            if stored_readiness is not None
            else _domain_readiness(facts)  # pre-H05 snapshots: recompute on read
        )
        domains.append(DomainView(
            domain=d.get("domain", ""),
            priority=d.get("priority", "medium"),
            state=d.get("state", "gap"),
            facts=facts,
            readiness=readiness,
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
