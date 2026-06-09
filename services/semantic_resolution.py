"""
Governed semantic resolution — Phase 1 model layer.

Turns a parsed `DrugMention` + candidate entities into a *governed decision*, not
a "matched / unmatched" boolean. It answers the red-team challenge's eight
questions per mention:

  1. extracted text         -> mention.original_text
  2. could refer to         -> candidates
  3. at what level          -> ResolutionDecision.match_level
  4. confirmed/inferred/missing/contradictory -> attribute_comparison
  5. alternatives           -> rejected_candidates
  6. why this one           -> decision_reason
  7. confidence + why       -> confidence_breakdown (14 explainable dims)
  8. auto/review/escalate   -> routing

It is **pure** (no DB / no I/O): callers pass candidate attributes (sourced from
the drugs table, an ontology cross-walk, or any combination of sources). That is
deliberate — the same model governs single-source and multi-source resolution.
Behaviour is driven by a `ResolutionPolicy` so the *same* engine can run a
commercial use-case (keep every presentation distinct) or an epidemiology
use-case (roll up to ingredient) without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from domain.pharma.drug_mention_parser import DrugMention, Quantity


# ============================================================
# Identity levels (the hierarchy a match can be made AT)
# ============================================================

class MatchLevel(str, Enum):
    """Identity levels, canonical names per domain_pack_raw.md §2.

    A combination is a product-level concept; strength/concentration/form/route/
    pack collapse to configuration level; brand+market is market-authorisation.
    """
    NONE = "none"
    INGREDIENT = "ingredient_level"                 # same active substance only
    PRODUCT = "product_level"                        # same product concept (incl. combo, brand)
    CONFIGURATION = "configuration_level"            # + form + route + strength/conc/pack
    MARKET_AUTHORISATION = "market_authorisation_level"  # + market + label/regulatory id
    REGIMEN = "regimen_level"                        # treatment instruction, NOT identity

    @property
    def rank(self) -> int:
        order = [self.NONE, self.INGREDIENT, self.PRODUCT, self.CONFIGURATION,
                 self.MARKET_AUTHORISATION]
        return order.index(self) if self in order else 0


class AttributeStatus(str, Enum):
    CONFIRMED = "confirmed"        # mention specifies it, candidate agrees
    INFERRED = "inferred"          # agreement, but mention value was inferred
    MISSING = "missing"            # mention specifies it, candidate lacks it
    CONTRADICTORY = "contradictory"  # both present, disagree
    IRRELEVANT = "irrelevant"      # mention does not specify it


class AmbiguityFlag(str, Enum):
    """Canonical flag vocabulary per domain_pack_raw.md §8 (stewardship triggers)."""
    MONO_COMBO_AMBIGUITY = "MONO_COMBO_AMBIGUITY"
    DOSE_VOLUME_CONFUSION = "DOSE_VOLUME_CONFUSION"
    FORM_ROUTE_CONFLICT = "FORM_ROUTE_CONFLICT"
    FORMULATION_CONFLICT = "FORMULATION_CONFLICT"
    MISSING_STRENGTH = "MISSING_STRENGTH"
    CONCENTRATION_MISMATCH = "CONCENTRATION_MISMATCH"
    PACK_VOLUME_MISMATCH = "PACK_VOLUME_MISMATCH"
    VOLUME_NOT_STRENGTH = "VOLUME_NOT_STRENGTH"
    BRAND_GENERIC_CONFLICT = "BRAND_GENERIC_CONFLICT"
    INFERRED_ATTRIBUTE_USED = "INFERRED_ATTRIBUTE_USED"
    SALT_VARIANT = "SALT_VARIANT"
    CONTEXT_NOT_PRODUCT = "CONTEXT_NOT_PRODUCT"
    LOW_CANDIDATE_SEPARATION = "LOW_CANDIDATE_SEPARATION"
    SOURCE_LOW_TRUST = "SOURCE_LOW_TRUST"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"


# Critical flags force escalation — never auto-resolve over these
# (domain_pack_raw.md §7 penalties marked critical:true).
HIGH_RISK_FLAGS = frozenset({
    AmbiguityFlag.MONO_COMBO_AMBIGUITY,
    AmbiguityFlag.DOSE_VOLUME_CONFUSION,
    AmbiguityFlag.FORM_ROUTE_CONFLICT,
    AmbiguityFlag.FORMULATION_CONFLICT,
    AmbiguityFlag.CONTRADICTORY_EVIDENCE,
})


# ============================================================
# Candidate + policy
# ============================================================

@dataclass
class CandidateEntity:
    """Source-agnostic view of a candidate identity's typed attributes.

    Populated from the drugs table, an ontology node (RxNorm/ATC), or merged
    multi-source attributes. `attribute_sources` records provenance per attribute
    so the engine can mark inferred/low-trust evidence.
    """
    entity_id: str
    entity_type: str = "drug"
    name: str = ""
    components: list[str] = field(default_factory=list)
    is_combination: bool = False
    formulation: Optional[str] = None
    route: Optional[str] = None
    strength: Optional[Quantity] = None
    concentration: Optional[Quantity] = None
    volume: Optional[Quantity] = None
    brand: Optional[str] = None
    market: Optional[str] = None
    is_standalone_substance: bool = False  # has its own mono row in the substrate
    source_reliability: float = 0.7        # trust tier of the candidate's source
    attribute_sources: dict = field(default_factory=dict)
    richness: int = 0                      # facts+trials, tie-breaker


@dataclass
class ResolutionPolicy:
    """The configurable 'modular' surface — per use-case / market / tenant."""
    auto_resolve_threshold: float = 0.85
    min_margin_over_second: float = 0.15
    # which levels' required attributes must be present to auto-resolve at level
    required_for_clinical_drug: bool = True
    collapse_salt: bool = False        # may a salt form fold into the base compound?
    collapse_release: bool = False     # may ER fold into IR?
    distinguish_market: bool = True
    distinguish_formulation: bool = True
    distinguish_route: bool = True
    low_source_reliability: float = 0.5
    # components that legitimately exist ONLY as a combination (e.g. sacubitril →
    # Entresto). A mono mention of one of these may resolve to the combo without a
    # MONO_COMBO_AMBIGUITY flag; any other mono name landing on a combo is flagged.
    combo_only_components: frozenset = field(default_factory=frozenset)
    # explainable weights for the confidence breakdown
    weights: dict = field(default_factory=lambda: {
        "text_similarity": 1.0, "ontology_support": 1.0, "ingredient": 3.0,
        "brand_generic": 1.0, "formulation": 1.0, "route": 1.0, "strength": 1.5,
        "concentration": 1.5, "volume_pack": 0.5, "market": 0.5,
        "source_reliability": 1.0, "extraction_quality": 0.5,
    })


DEFAULT_POLICY = ResolutionPolicy()


# ============================================================
# Confidence breakdown (explainable, not a magic number)
# ============================================================

@dataclass
class ConfidenceBreakdown:
    text_similarity: float = 0.0
    ontology_support: float = 0.0
    ingredient: float = 0.0
    brand_generic: float = 0.0
    formulation: float = 0.0
    route: float = 0.0
    strength: float = 0.0
    concentration: float = 0.0
    volume_pack: float = 0.0
    market: float = 0.0
    source_reliability: float = 0.0
    extraction_quality: float = 0.0
    ambiguity_penalty: float = 0.0   # subtractive
    risk_penalty: float = 0.0        # subtractive
    # which dims actually applied (mention specified them) — only these are averaged
    _relevant: set = field(default_factory=set)

    def final(self, weights: dict) -> float:
        num = den = 0.0
        for dim, w in weights.items():
            if dim in self._relevant:
                num += w * getattr(self, dim, 0.0)
                den += w
        base = (num / den) if den else 0.0
        score = base - self.ambiguity_penalty - self.risk_penalty
        return max(0.0, min(1.0, round(score, 4)))

    def as_dict(self) -> dict:
        return {k: round(v, 4) for k, v in self.__dict__.items()
                if not k.startswith("_") and isinstance(v, float)}


# ============================================================
# The decision (output contract)
# ============================================================

@dataclass
class ResolutionDecision:
    extracted_text: str
    normalised_text: str
    extracted_attributes: dict
    selected_entity_id: Optional[str]
    selected_entity_type: Optional[str]
    match_level: MatchLevel
    confidence_score: float
    confidence_breakdown: dict
    attribute_comparison: dict           # attr -> AttributeStatus value
    ambiguity_flags: list                 # list[str]
    rejected_candidates: list             # [{entity_id, score, reason}]
    decision_reason: str
    auto_resolved: bool
    steward_review_required: bool
    review_priority: str                  # 'none'|'low'|'medium'|'high'
    routing: str                          # 'auto'|'review'|'escalate'


# ============================================================
# Comparison + scoring helpers (pure)
# ============================================================

def _qty_equal(a: Optional[Quantity], b: Optional[Quantity], tol: float = 1e-6) -> Optional[bool]:
    """None if either missing; else True/False on (kind, unit, value)."""
    if a is None or b is None:
        return None
    if a.kind != b.kind or a.unit != b.unit:
        return False
    if a.value is None or b.value is None:
        return None
    return abs(a.value - b.value) <= tol + 1e-3 * max(abs(a.value), abs(b.value))


def _components_relation(m: DrugMention, c: CandidateEntity) -> str:
    """'equal' | 'subset' (mention ⊂ candidate) | 'overlap' | 'disjoint'."""
    mw = {x.lower() for x in m.components}
    cw = {x.lower() for x in c.components}
    if not mw or not cw:
        return "disjoint"
    if mw == cw:
        return "equal"
    if mw.issubset(cw):
        return "subset"
    if mw & cw:
        return "overlap"
    return "disjoint"


def compare_attributes(m: DrugMention, c: CandidateEntity) -> dict:
    """Per-attribute confirmed / inferred / missing / contradictory / irrelevant."""
    out: dict[str, AttributeStatus] = {}

    rel = _components_relation(m, c)
    if rel in ("equal", "subset"):
        out["substance"] = AttributeStatus.CONFIRMED
    elif rel == "overlap":
        out["substance"] = AttributeStatus.CONTRADICTORY
    else:
        out["substance"] = AttributeStatus.MISSING if not c.components else AttributeStatus.CONTRADICTORY

    # combination
    if m.is_combination:
        out["combination"] = (AttributeStatus.CONFIRMED if c.is_combination
                              and rel == "equal" else AttributeStatus.CONTRADICTORY
                              if not c.is_combination else AttributeStatus.MISSING)
    else:
        out["combination"] = AttributeStatus.IRRELEVANT

    def _cmp_scalar(mv, cv, inferred=False):
        if mv is None:
            return AttributeStatus.IRRELEVANT
        if cv is None:
            return AttributeStatus.MISSING
        if str(mv).lower() == str(cv).lower():
            return AttributeStatus.INFERRED if inferred else AttributeStatus.CONFIRMED
        return AttributeStatus.CONTRADICTORY

    out["formulation"] = _cmp_scalar(m.formulation, c.formulation)
    out["route"] = _cmp_scalar(m.route, c.route, inferred=m.route_inferred)

    for attr in ("strength", "concentration", "volume"):
        mv, cv = getattr(m, attr), getattr(c, attr)
        eq = _qty_equal(mv, cv)
        if mv is None:
            out[attr] = AttributeStatus.IRRELEVANT
        elif cv is None:
            out[attr] = AttributeStatus.MISSING
        elif eq is True:
            out[attr] = AttributeStatus.CONFIRMED
        elif eq is False:
            out[attr] = AttributeStatus.CONTRADICTORY
        else:
            out[attr] = AttributeStatus.MISSING

    out["brand"] = _cmp_scalar(m.brand, c.brand)
    return out


def determine_match_level(comparison: dict, m: DrugMention, c: CandidateEntity) -> MatchLevel:
    """Most specific level at which every mention-specified attribute is confirmed."""
    def ok(attr):
        return comparison.get(attr) in (AttributeStatus.CONFIRMED, AttributeStatus.INFERRED)
    def not_contra(attr):
        return comparison.get(attr) != AttributeStatus.CONTRADICTORY

    if comparison.get("substance") not in (AttributeStatus.CONFIRMED, AttributeStatus.INFERRED):
        return MatchLevel.NONE
    # any hard contradiction on a specified attribute caps the level at ingredient
    specified = m.present_attributes()
    contradicted = any(comparison.get(a) == AttributeStatus.CONTRADICTORY
                       for a in ("formulation", "route", "strength", "concentration", "volume"))

    # regimen-only mention with no substance is a treatment instruction, not identity
    if not m.substance and (m.regimen_flags or m.context_flags):
        return MatchLevel.REGIMEN

    level = MatchLevel.INGREDIENT
    if (m.is_combination and ok("combination")) or ("brand" in specified and ok("brand")):
        level = MatchLevel.PRODUCT
    if not contradicted:
        has_form_or_route = ok("formulation") or ok("route")
        has_dose = ok("strength") or ok("concentration") or ok("volume")
        if has_form_or_route and has_dose:
            level = MatchLevel.CONFIGURATION
    if level == MatchLevel.CONFIGURATION and c.market and ok("brand"):
        level = MatchLevel.MARKET_AUTHORISATION
    return level


def detect_ambiguity(m: DrugMention, c: CandidateEntity, comparison: dict,
                     candidates: list, policy: ResolutionPolicy) -> list:
    flags: list[AmbiguityFlag] = []

    # Mono mention landing on a combination. Per domain_pack_raw.md §4: flag
    # unless (no standalone owner is available) AND (the component is pack-marked
    # combo-only, e.g. sacubitril→Entresto). So metformin→combo with only the
    # combo offered is flagged (metformin is normally standalone); sacubitril→
    # combo is not (it exists only as a combination).
    if not m.is_combination and c.is_combination:
        owner_exists = any(getattr(cc, "is_standalone_substance", False)
                           and not cc.is_combination for cc in candidates)
        combo_only = any(comp.lower() in policy.combo_only_components
                         for comp in m.components)
        if owner_exists or not combo_only:
            flags.append(AmbiguityFlag.MONO_COMBO_AMBIGUITY)

    # mention carries a volume (mL) — must never be read as strength
    if m.volume is not None:
        flags.append(AmbiguityFlag.VOLUME_NOT_STRENGTH)
    # dose vs volume: mention has volume but candidate models it as strength
    if comparison.get("strength") == AttributeStatus.CONTRADICTORY and (m.volume or m.concentration):
        flags.append(AmbiguityFlag.DOSE_VOLUME_CONFUSION)
    if comparison.get("concentration") == AttributeStatus.CONTRADICTORY:
        flags.append(AmbiguityFlag.CONCENTRATION_MISMATCH)
    if comparison.get("volume") == AttributeStatus.CONTRADICTORY:
        flags.append(AmbiguityFlag.PACK_VOLUME_MISMATCH)

    if comparison.get("formulation") == AttributeStatus.CONTRADICTORY and policy.distinguish_formulation:
        flags.append(AmbiguityFlag.FORMULATION_CONFLICT)
    if comparison.get("route") == AttributeStatus.CONTRADICTORY and policy.distinguish_route:
        flags.append(AmbiguityFlag.FORM_ROUTE_CONFLICT)

    # missing-but-required strength for a product-configuration interpretation
    if comparison.get("strength") == AttributeStatus.MISSING or (
            policy.required_for_clinical_drug and m.strength and not c.strength):
        flags.append(AmbiguityFlag.MISSING_STRENGTH)

    if m.route_inferred and comparison.get("route") == AttributeStatus.INFERRED:
        flags.append(AmbiguityFlag.INFERRED_ATTRIBUTE_USED)

    if m.salt_tokens and not policy.collapse_salt:
        flags.append(AmbiguityFlag.SALT_VARIANT)

    if m.context_flags:  # negation / switch / dose-change => may not be product identity
        flags.append(AmbiguityFlag.CONTEXT_NOT_PRODUCT)

    if m.brand and comparison.get("brand") == AttributeStatus.CONTRADICTORY:
        flags.append(AmbiguityFlag.BRAND_GENERIC_CONFLICT)

    if comparison.get("substance") == AttributeStatus.CONTRADICTORY:
        flags.append(AmbiguityFlag.CONTRADICTORY_EVIDENCE)

    if c.source_reliability < policy.low_source_reliability:
        flags.append(AmbiguityFlag.SOURCE_LOW_TRUST)

    return flags


def _score(m: DrugMention, c: CandidateEntity, comparison: dict,
           flags: list, policy: ResolutionPolicy) -> ConfidenceBreakdown:
    b = ConfidenceBreakdown()
    rel = _components_relation(m, c)
    b.ingredient = 1.0 if rel == "equal" else 0.8 if rel == "subset" else 0.0
    b.text_similarity = 1.0 if c.name and m.normalized_text and \
        m.normalized_text.lower() in c.name.lower() else 0.5
    b.ontology_support = 0.6  # placeholder until ontology cross-walk wired (Phase 2)
    b.source_reliability = c.source_reliability
    b.extraction_quality = 0.5 if m.context_flags else 0.9
    b._relevant.update({"ingredient", "text_similarity", "ontology_support",
                        "source_reliability", "extraction_quality"})

    def grade(attr):
        st = comparison.get(attr)
        if st == AttributeStatus.CONFIRMED:
            return 1.0
        if st == AttributeStatus.INFERRED:
            return 0.7
        if st == AttributeStatus.MISSING:
            return 0.4
        if st == AttributeStatus.CONTRADICTORY:
            return 0.0
        return None  # irrelevant

    for attr, dim in (("formulation", "formulation"), ("route", "route"),
                      ("strength", "strength"), ("concentration", "concentration"),
                      ("volume", "volume_pack"), ("brand", "brand_generic")):
        g = grade(attr)
        if g is not None:
            setattr(b, dim, g)
            b._relevant.add(dim)

    if m.brand:
        b.brand_generic = 1.0 if comparison.get("brand") == AttributeStatus.CONFIRMED else 0.0
        b._relevant.add("brand_generic")

    # penalties
    b.ambiguity_penalty = min(0.4, 0.1 * len([f for f in flags if f not in HIGH_RISK_FLAGS]))
    b.risk_penalty = 0.5 if any(f in HIGH_RISK_FLAGS for f in flags) else 0.0
    return b


def _route(flags: list, final: float, margin: float, policy: ResolutionPolicy,
           multiple_close: bool) -> tuple[str, bool, str]:
    """Return (routing, review_required, priority)."""
    if any(f in HIGH_RISK_FLAGS for f in flags):
        return "escalate", True, "high"
    review_triggers = {
        AmbiguityFlag.MISSING_STRENGTH, AmbiguityFlag.CONCENTRATION_MISMATCH,
        AmbiguityFlag.PACK_VOLUME_MISMATCH, AmbiguityFlag.VOLUME_NOT_STRENGTH,
        AmbiguityFlag.INFERRED_ATTRIBUTE_USED, AmbiguityFlag.CONTEXT_NOT_PRODUCT,
        AmbiguityFlag.SALT_VARIANT, AmbiguityFlag.SOURCE_LOW_TRUST,
        AmbiguityFlag.BRAND_GENERIC_CONFLICT, AmbiguityFlag.LOW_CANDIDATE_SEPARATION,
    }
    needs_review = (multiple_close or margin < policy.min_margin_over_second
                    or final < policy.auto_resolve_threshold
                    or any(f in review_triggers for f in flags))
    if needs_review:
        priority = "medium" if final >= 0.6 else "high"
        return "review", True, priority
    return "auto", False, "none"


def resolve_mention(m: DrugMention, candidates: list,
                   policy: ResolutionPolicy = DEFAULT_POLICY) -> ResolutionDecision:
    """Top-level: score every candidate, pick the best, govern the decision."""
    extracted = {
        "substance": m.substance, "components": m.components,
        "is_combination": m.is_combination, "formulation": m.formulation,
        "route": m.route, "route_inferred": m.route_inferred,
        "strength": m.strength.__dict__ if m.strength else None,
        "concentration": m.concentration.__dict__ if m.concentration else None,
        "volume": m.volume.__dict__ if m.volume else None,
        "brand": m.brand, "regimen_flags": m.regimen_flags,
        "context_flags": m.context_flags, "salt_tokens": m.salt_tokens,
    }

    if not candidates:
        return ResolutionDecision(
            extracted_text=m.original_text, normalised_text=m.normalized_text,
            extracted_attributes=extracted, selected_entity_id=None,
            selected_entity_type=None, match_level=MatchLevel.NONE,
            confidence_score=0.0, confidence_breakdown={},
            attribute_comparison={}, ambiguity_flags=[], rejected_candidates=[],
            decision_reason="No candidate entities supplied.", auto_resolved=False,
            steward_review_required=True, review_priority="medium", routing="review")

    scored = []
    for c in candidates:
        comp = compare_attributes(m, c)
        flags = detect_ambiguity(m, c, comp, candidates, policy)
        bd = _score(m, c, comp, flags, policy)
        final = bd.final(policy.weights)
        scored.append((c, comp, flags, bd, final))

    # rank by final, tie-break on richness
    scored.sort(key=lambda t: (t[4], t[0].richness), reverse=True)
    best_c, comp, flags, bd, final = scored[0]
    second = scored[1][4] if len(scored) > 1 else 0.0
    margin = round(final - second, 4)
    multiple_close = len(scored) > 1 and margin < policy.min_margin_over_second
    if multiple_close and AmbiguityFlag.LOW_CANDIDATE_SEPARATION not in flags:
        flags = flags + [AmbiguityFlag.LOW_CANDIDATE_SEPARATION]

    level = determine_match_level(comp, m, best_c)
    routing, review_required, priority = _route(flags, final, margin, policy, multiple_close)
    auto = routing == "auto"

    reason_bits = [f"substance={comp['substance'].value}", f"level={level.value}",
                   f"score={final}", f"margin={margin}"]
    if flags:
        reason_bits.append("flags=" + ",".join(f.value for f in flags))
    decision_reason = "Selected " + (best_c.name or best_c.entity_id) + " — " + "; ".join(reason_bits)

    return ResolutionDecision(
        extracted_text=m.original_text,
        normalised_text=m.normalized_text,
        extracted_attributes=extracted,
        selected_entity_id=best_c.entity_id,
        selected_entity_type=best_c.entity_type,
        match_level=level,
        confidence_score=final,
        confidence_breakdown=bd.as_dict(),
        attribute_comparison={k: v.value for k, v in comp.items()},
        ambiguity_flags=[f.value for f in flags],
        rejected_candidates=[
            {"entity_id": c.entity_id, "score": sc,
             "reason": "lower score" if sc < final else "tie"}
            for (c, _cmp, _fl, _bd, sc) in scored[1:]
        ],
        decision_reason=decision_reason,
        auto_resolved=auto,
        steward_review_required=review_required,
        review_priority=priority,
        routing=routing,
    )
