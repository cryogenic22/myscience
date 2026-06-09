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

import pathlib
from dataclasses import dataclass, field
from typing import Optional

import yaml

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


def _base_score(conf: dict, method: str) -> float:
    key = _METHOD_BASE.get(method, method)
    return conf["base"].get(key, conf["base"]["fuzzy_only"])


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

    # 3. Confidence: base (by method) + boosts - penalties.
    method = c.method or _default_method(c)
    base = _base_score(conf, method)
    boosts = penalties = 0.0
    bd = {"base": base, "method": method}

    def add_pen(key):
        nonlocal penalties
        p = conf["penalties"].get(key, 0.0)
        penalties += p
        bd[f"penalty.{key}"] = -p

    if c.many_to_many:
        flags.append("RXNORM_ATC_MANY_TO_MANY")
        add_pen("many_to_many_mapping")
        relation = "related"  # never assert exact identity on a many-to-many
    if c.combination or c.tty == "MIN":
        flags.append("COMBINATION_COMPONENT_AMBIGUITY")
        add_pen("combination_product")
    if c.stale_source:
        add_pen("stale_external_release")
    if c.from_system == "atc" and c.level is not None and c.level <= 3 \
            and c.to_target in ("molecule", "drug_class"):
        # using a broad ATC level for a more specific internal target
        add_pen("atc_level_too_broad_for_task")

    if c.curator_approved:
        boosts += conf["boosts"]["human_curator_approved"]
        bd["boost.curator"] = conf["boosts"]["human_curator_approved"]
    if c.multi_source:
        boosts += conf["boosts"]["multiple_source_agreement"]
        bd["boost.multi_source"] = conf["boosts"]["multiple_source_agreement"]

    final = max(0.0, min(1.0, round(base + boosts - penalties, 4)))
    bd["final"] = final

    # 4. Action from bands + critical-flag cap.
    critical = set(pack.get("critical_flags", []))
    has_critical = any(f in critical for f in flags)
    bands = conf["bands"]
    if final < bands["review_required"]:
        action = "rejected_or_quarantined"
    elif has_critical or c.many_to_many:
        action = "review_required"            # never auto over a critical flag
    elif final >= bands["approved_auto"]:
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
