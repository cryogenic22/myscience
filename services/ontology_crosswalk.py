"""
Governed RxNorm/ATC -> internal ontology crosswalk engine (Loop L1, Phase a).

Pure, DB-free classifier: given a candidate mapping between an internal entity and
an external concept (an RxNorm term-type or an ATC level), it returns a governed
CrosswalkRecord — relation, scope, an explainable confidence, ambiguity flags and
an auto/audit/review/reject action — per domain/pharma/packs/pharma_rxnorm_atc_crosswalk.yaml.

The hard rules it enforces (SME, docs/pharmcore_atc.md):
  * RxNorm is for clinical-drug identity; ATC is for class reasoning ONLY.
  * A mapping ENRICHES the internal ontology — it never overwrites identity.
  * Forbidden bridges (ATC-class -> exact product, ATC -> pricing/payer, RxNorm
    SCD/SBD -> exact ATC reverse, RxNorm brand -> market authorisation) are
    refused outright.
  * Many-to-many is never silently collapsed — it is flagged and routed to review.

The loaders that pull real RxCUI/ATC concepts and the crosswalk_records table are
Loop L1b; this engine is the governed core they feed.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_PACK_PATH = (pathlib.Path(__file__).parent.parent
              / "domain" / "pharma" / "packs" / "pharma_rxnorm_atc_crosswalk.yaml")


def load_crosswalk_pack(path: Optional[pathlib.Path] = None) -> dict:
    return yaml.safe_load((path or _PACK_PATH).read_text(encoding="utf-8"))


# ============================================================
# Input / output
# ============================================================

@dataclass
class CrosswalkCandidate:
    """A proposed mapping to classify.

    from_system : 'rxnorm' | 'atc'
    tty         : RxNorm term type (IN/PIN/MIN/BN/SCD/SBD/GPCK/BPCK/DF) — rxnorm only
    level       : ATC level 1..5 — atc only
    to_target   : the INTENT of the mapping — what it is being used to assert.
                  Legal targets come from the tty/level maps (molecule, drug_class,
                  component_set, ...). Illegal intents (exact_product, brand,
                  pricing_configuration, payer_policy_product, atc_exact_reverse,
                  market_authorisation) trip a forbidden bridge.
    method      : how the mapping was found (exact_identifier / atc_hierarchy / ...)
    """
    from_system: str
    to_target: str
    tty: Optional[str] = None
    level: Optional[int] = None
    method: Optional[str] = None
    internal_entity_id: Optional[str] = None
    external_id: Optional[str] = None
    many_to_many: bool = False
    combination: bool = False
    stale_source: bool = False
    curator_approved: bool = False
    multi_source: bool = False
    precise_ingredient_conflict: bool = False   # salt/precise-ingredient changes identity
    route_formulation_dependent: bool = False   # classification depends on route/form
    source_curated: bool = False                # mapping from a curated crosswalk source
    ingredient_class_aligned: bool = False       # ingredient + class agree (boost)


@dataclass
class CrosswalkRecord:
    relation: str                     # exact|narrower|broader|related|inferred|rejected
    scope: Optional[str]
    confidence: float
    confidence_breakdown: dict
    flags: list = field(default_factory=list)
    action: str = "review_required"   # approved_auto|approved_with_audit|review_required|rejected_or_quarantined
    reason: str = ""


# ============================================================
# Classification (pure)
# ============================================================

def _matched_forbidden(c: CrosswalkCandidate, pack: dict) -> Optional[str]:
    """Return the critical flag if the candidate trips a forbidden bridge."""
    for fb in pack.get("forbidden_bridges", []) or []:
        if fb.get("from_system") != c.from_system:
            continue
        if fb.get("to_target") != c.to_target:
            continue
        if "from_tty" in fb and fb["from_tty"] != c.tty:
            continue
        if "from_level" in fb and fb["from_level"] != c.level:
            continue
        return fb.get("flag")
    return None


def _default_method(c: CrosswalkCandidate) -> str:
    return "hierarchy_rollup" if c.from_system == "atc" else "exact_name_plus_term_type_match"


# Short canonical method names (SME mapping_method_enum) -> confidence base keys.
_METHOD_BASE = {
    "exact_identifier": "exact_identifier_loaded_from_source",
    "exact_name": "exact_name_plus_term_type_match",
    "rxnorm_relationship": "exact_name_plus_term_type_match",
    "approved_alias": "approved_alias_match",
    "synonym_match": "approved_alias_match",
    "atc_hierarchy": "hierarchy_rollup",
    "external_source_crosswalk": "hierarchy_rollup",
    "model_suggested": "model_suggested_name_match",
}


def _base_score(conf: dict, method: str) -> tuple[float, bool]:
    """Return (base_score, method_known). An unrecognised method degrades to
    fuzzy_only AND reports method_known=False so the caller can flag it (a typo'd
    method must not silently masquerade as a fuzzy match)."""
    key = _METHOD_BASE.get(method, method)
    if key in conf["base"]:
        return conf["base"][key], True
    return conf["base"]["fuzzy_only"], False


# Intents that assert product/identity grade — an ATC (class) source can never
# legitimately supply these, so the allowlist refuses them with a precise flag.
_IDENTITY_GRADE_TARGETS = {
    "exact_product", "brand", "product_configuration", "configuration",
    "branded_product_configuration", "market_authorisation", "pack",
    "product_pack", "branded_product_pack",
}


def _allowlist_violation_flag(c: CrosswalkCandidate) -> str:
    """The critical flag for a to_target the source concept may not assert."""
    if c.to_target == "pricing_configuration":
        return "PRICING_REQUIRES_CONFIGURATION_NOT_ATC"
    if c.to_target == "payer_policy_product":
        return "PAYER_POLICY_CLASS_NOT_EQUAL_ATC_CLASS"
    if c.from_system == "atc" and c.to_target in _IDENTITY_GRADE_TARGETS:
        return "PRODUCT_CONFIGURATION_REQUIRED_BUT_ONLY_ATC_AVAILABLE"
    if c.from_system == "atc":
        return "ATC_TOO_BROAD_FOR_EXACT_MATCH"
    return "TARGET_EXCEEDS_SOURCE_IDENTITY_GRADE"


def classify(c: CrosswalkCandidate, pack: Optional[dict] = None) -> CrosswalkRecord:
    pack = pack or load_crosswalk_pack()
    conf = pack["confidence"]
    flags: list[str] = []

    # 1. Forbidden bridge — refuse outright (the cardinal sins).
    fb_flag = _matched_forbidden(c, pack)
    if fb_flag:
        return CrosswalkRecord(
            relation="rejected", scope=None, confidence=0.0,
            confidence_breakdown={"forbidden_bridge": fb_flag},
            flags=[fb_flag], action="rejected_or_quarantined",
            reason=f"Forbidden bridge {c.from_system}->{c.to_target}: {fb_flag}.")

    # 2. Default relation/scope from the term-type / ATC-level map.
    if c.from_system == "rxnorm":
        m = (pack.get("rxnorm_tty") or {}).get(c.tty)
        target_label = c.tty
    elif c.from_system == "atc":
        m = (pack.get("atc_level") or {}).get(c.level)
        target_label = f"ATC L{c.level}"
    else:
        m = None
        target_label = c.from_system
    if not m:
        return CrosswalkRecord(
            relation="rejected", scope=None, confidence=0.0, confidence_breakdown={},
            flags=["UNKNOWN_EXTERNAL_CONCEPT"], action="rejected_or_quarantined",
            reason=f"Unknown external concept: {target_label}.")
    relation, scope = m["relation"], m["scope"]

    # 2b. Allowlist gate — relation/scope come from the source concept, but the
    # to_target INTENT must be one the source may legitimately assert. A substance
    # concept cannot assert a price; an ATC class cannot assert a product. This
    # (not just the enumerated forbidden_bridges) is what stops the cardinal sins.
    allowed = m.get("allowed_targets")
    if allowed is not None and c.to_target not in allowed:
        flag = _allowlist_violation_flag(c)
        return CrosswalkRecord(
            relation="rejected", scope=None, confidence=0.0,
            confidence_breakdown={"allowlist_violation": flag, "allowed_targets": allowed},
            flags=[flag], action="rejected_or_quarantined",
            reason=f"{target_label} may not assert to_target='{c.to_target}' "
                   f"(allowed: {allowed}): {flag}.")

    # 3. Confidence: base (by method) + boosts - penalties.
    method = c.method or _default_method(c)
    base, method_known = _base_score(conf, method)
    boosts = penalties = 0.0
    bd = {"base": base, "method": method}
    if not method_known:
        flags.append("UNKNOWN_MAPPING_METHOD")

    def add_pen(key):
        nonlocal penalties
        p = conf["penalties"].get(key, 0.0)
        penalties += p
        bd[f"penalty.{key}"] = -p

    def add_boost(key):
        nonlocal boosts
        b = conf["boosts"].get(key, 0.0)
        boosts += b
        bd[f"boost.{key}"] = b

    if c.many_to_many:
        flags.append("RXNORM_ATC_MANY_TO_MANY")
        add_pen("many_to_many_mapping")
        relation = "related"  # never assert exact identity on a many-to-many
    if c.combination or c.tty == "MIN":
        flags.append("COMBINATION_COMPONENT_AMBIGUITY")
        add_pen("combination_product")
        if relation == "exact":
            relation = "related"  # never assert exact on an ambiguous combination
    if c.precise_ingredient_conflict:
        flags.append("PRECISE_INGREDIENT_CONFLICT")
        add_pen("ingredient_salt_or_precise_ingredient_conflict")
    if c.route_formulation_dependent:
        flags.append("ROUTE_FORMULATION_DEPENDENT_CLASSIFICATION")
        add_pen("route_or_formulation_dependency")
    if c.stale_source:
        add_pen("stale_external_release")
    if c.from_system == "atc" and c.level is not None and c.level <= 3 \
            and c.to_target in ("molecule", "drug_class"):
        add_pen("atc_level_too_broad_for_task")

    if c.curator_approved:
        add_boost("human_curator_approved")
    if c.multi_source:
        add_boost("multiple_source_agreement")
    if c.source_curated:
        add_boost("source_curated_crosswalk")
    if c.ingredient_class_aligned:
        add_boost("exact_ingredient_and_class_alignment")

    final = max(0.0, min(1.0, round(base + boosts - penalties, 4)))
    bd["final"] = final

    # 4. Action from bands + caps. A critical flag or a many-to-many can never
    # auto; a STALE external release can never reach approved_auto (the pack's
    # "current source" gate).
    critical = set(pack.get("critical_flags", []))
    has_critical = any(f in critical for f in flags)
    bands = conf["bands"]
    if final < bands["review_required"]:
        action = "rejected_or_quarantined"
    elif has_critical or c.many_to_many:
        action = "review_required"            # never auto over a critical flag
    elif final >= bands["approved_auto"] and not c.stale_source:
        action = "approved_auto"
    elif final >= bands["approved_with_audit"]:
        action = "approved_with_audit"
    else:
        action = "review_required"

    return CrosswalkRecord(
        relation=relation, scope=scope, confidence=final, confidence_breakdown=bd,
        flags=flags, action=action,
        reason=f"{target_label}->{c.to_target}: relation={relation}, scope={scope}, "
               f"conf={final}" + (f", flags={flags}" if flags else ""))


# ============================================================
# Read path — crosswalk evidence for a resolved entity
# ============================================================

_ONTOLOGY_CODES_SQL = """
    SELECT external_system, external_id, external_label,
           mapping_relation, mapping_scope, mapping_confidence
      FROM crosswalk_records
     WHERE internal_entity_id = %s
       AND record_status = 'active'
       AND (valid_to IS NULL OR valid_to > now())
       AND mapping_relation <> 'rejected'
     ORDER BY mapping_confidence DESC NULLS LAST
"""


def fetch_ontology_codes(db, internal_entity_id: str) -> list[dict]:
    """Active, non-rejected crosswalk records for an entity, as the dict shape
    CandidateEntity.ontology_codes / ontology_support_score expect:
    {system, code, label, relation, scope, confidence}.

    Read-only. Returns [] on any DB error (the resolver degrades to the neutral
    ontology_support rather than failing the whole resolution)."""
    try:
        rows = db.fetch_all(_ONTOLOGY_CODES_SQL, [str(internal_entity_id)])
    except Exception:
        logger.exception("fetch_ontology_codes failed for %s", internal_entity_id)
        return []
    out: list[dict] = []
    for r in rows or []:
        conf = r.get("mapping_confidence")
        try:
            conf = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            conf = 0.0
        out.append({
            "system": r.get("external_system"),
            "code": r.get("external_id"),
            "label": r.get("external_label"),
            "relation": r.get("mapping_relation"),
            "scope": r.get("mapping_scope"),
            "confidence": conf,
        })
    return out
