"""
Typed drug-mention parser — governed semantic resolution, Phase 1.

Where `mention_normalizer.normalize_drug_mention` *strips* strength / formulation
/ route to collapse a mention to a base name, this parser *preserves and types*
every attribute so downstream resolution can answer "at what level does this
match?" instead of "matched / unmatched".

    "semaglutide 2.5 mg/mL pen, once weekly"
        substance      = "semaglutide"        (mono)
        concentration  = 2.5 mg/mL            (kind=concentration)
        formulation    = "pen"
        route          = "subcutaneous"       (inferred from pen)
        regimen_flags  = ["once_weekly"]
        original_text  = "semaglutide 2.5 mg/mL pen, once weekly"   (never lost)

The parser is **pure** (no DB / no I/O) and **configurable**: all term tables and
unit systems live in a `DrugLexicon` that callers can override per domain / market.
This is the foundation the semantic-resolution model (services/semantic_resolution.py)
scores and routes; it does not itself decide a match.

Reuses the existing dosage-form vocabulary from mention_normalizer rather than
forking it (anti-slop).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from domain.pharma.mention_normalizer import _DOSAGE_FORMS


# ============================================================
# Configurable lexicon (the "modular + configurable" surface)
# ============================================================

# Formulations (presentation forms) vs routes (administration paths). The legacy
# _DOSAGE_FORMS set mixes them; here we separate the two concerns because the
# challenge treats formulation and route as *distinct* attributes.
_DEFAULT_FORMULATIONS = {
    "tablet", "tablets", "capsule", "capsules", "injection", "injectable",
    "solution", "suspension", "cream", "ointment", "gel", "patch", "patches",
    "inhaler", "spray", "drops", "suppository", "powder", "granules", "syrup",
    "elixir", "emulsion", "lotion", "foam", "implant", "pen", "prefilled",
    "pre-filled", "autoinjector", "auto-injector", "vial", "ampoule",
    "cartridge", "device",
}

_DEFAULT_ROUTES = {
    "oral", "subcutaneous", "intramuscular", "intravenous", "ophthalmic",
    "nasal", "topical", "rectal", "sublingual", "buccal", "transdermal",
    "inhalation", "infusion", "subcut", "sc", "iv", "im", "po",
}

# Some formulations imply a route — recorded as an *inferred* (not confirmed)
# attribute so the confidence model can mark it accordingly.
_FORMULATION_ROUTE_HINT = {
    "pen": "subcutaneous", "autoinjector": "subcutaneous",
    "auto-injector": "subcutaneous", "prefilled": "subcutaneous",
    "tablet": "oral", "tablets": "oral", "capsule": "oral", "capsules": "oral",
    "inhaler": "inhalation", "patch": "transdermal", "cream": "topical",
    "ointment": "topical", "drops": "ophthalmic", "suppository": "rectal",
}

# Modified-release / variant qualifiers — kept as attributes, never silently
# folded (the challenge: do not collapse ER vs IR).
_DEFAULT_RELEASE = {
    "extended-release", "extended release", "delayed-release", "delayed release",
    "immediate-release", "immediate release", "modified-release",
    "sustained-release", "controlled-release", "er", "xr", "sr", "cr", "dr",
    "ir", "xl",
}

# Salt / variant tokens — flagged so resolution can refuse to collapse a salt
# form into the base compound unless the use-case policy allows it.
_DEFAULT_SALT_TOKENS = {
    "hydrochloride", "hcl", "sodium", "potassium", "calcium", "sulfate",
    "sulphate", "phosphate", "maleate", "mesylate", "besylate", "tartrate",
    "succinate", "fumarate", "citrate", "acetate", "hydrate", "anhydrous",
    "monohydrate", "dihydrate",
}

# Regimen / treatment-instruction phrases — these describe how a product is USED,
# not its identity. Kept separate so a regimen is never mistaken for a product.
_DEFAULT_REGIMEN = {
    "once weekly": "once_weekly", "weekly": "once_weekly",
    "once daily": "once_daily", "daily": "once_daily",
    "twice daily": "twice_daily", "bid": "twice_daily",
    "titration": "titration", "loading dose": "loading_dose",
    "maintenance dose": "maintenance", "maintenance": "maintenance",
    "starter pack": "starter_pack", "starter": "starter_pack",
    "sample pack": "sample_pack",
}

# Context phrases that signal the mention is an EVENT, not a product identity.
_DEFAULT_CONTEXT = {
    "not currently taking": "negation", "not taking": "negation",
    "discontinued": "negation", "stopped": "negation",
    "switched from": "switch", "switched to": "switch", "switch": "switch",
    "increased to": "dose_change", "decreased to": "dose_change",
    "increase": "dose_change", "increased": "dose_change",
    "supplied": "supply", "dispensed": "supply",
}

# Combination separators (NOT '/' alone — that also forms unit "mg/mL", handled
# by stripping quantities before combo-splitting).
_COMBO_SPLIT_RE = re.compile(r"\s*/\s*|\s+and\s+|\s+\+\s+|\s+plus\s+|\s+&\s+", re.IGNORECASE)

# Number words for "five milligrams" style mentions (modest, configurable).
_NUMBER_WORDS = {
    "half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20,
    "fifty": 50, "hundred": 100, "thousand": 1000,
}


@dataclass(frozen=True)
class DrugLexicon:
    """All term tables a parser needs — override per domain / market / use-case."""
    formulations: frozenset = field(default_factory=lambda: frozenset(_DEFAULT_FORMULATIONS))
    routes: frozenset = field(default_factory=lambda: frozenset(_DEFAULT_ROUTES))
    release_qualifiers: frozenset = field(default_factory=lambda: frozenset(_DEFAULT_RELEASE))
    salt_tokens: frozenset = field(default_factory=lambda: frozenset(_DEFAULT_SALT_TOKENS))
    regimen: dict = field(default_factory=lambda: dict(_DEFAULT_REGIMEN))
    context: dict = field(default_factory=lambda: dict(_DEFAULT_CONTEXT))
    formulation_route_hint: dict = field(default_factory=lambda: dict(_FORMULATION_ROUTE_HINT))
    # brand -> canonical generic. Empty by default (no guessing); supplied per pack.
    brands: dict = field(default_factory=dict)


DEFAULT_LEXICON = DrugLexicon()


# ============================================================
# Typed quantity model
# ============================================================

# Mass units -> milligrams.
_MASS_TO_MG = {"mg": 1.0, "milligram": 1.0, "milligrams": 1.0,
               "mcg": 0.001, "ug": 0.001, "µg": 0.001, "microgram": 0.001,
               "micrograms": 0.001, "g": 1000.0, "gram": 1000.0, "grams": 1000.0,
               "ng": 1e-6}
# Volume units -> millilitres.
_VOL_TO_ML = {"ml": 1.0, "milliliter": 1.0, "millilitre": 1.0, "milliliters": 1.0,
              "millilitres": 1.0, "l": 1000.0, "liter": 1000.0, "litre": 1000.0}
_ACTIVITY_UNITS = {"iu", "units", "unit", "u"}

_QUANTITY_KINDS = ("strength", "concentration", "volume", "activity", "percent", "count")


@dataclass
class Quantity:
    """A single typed, unit-normalised quantity with its raw source text."""
    raw: str                       # exact extracted text, never lost
    kind: str                      # one of _QUANTITY_KINDS
    value: Optional[float]         # in canonical unit, None if unparseable
    unit: str                      # canonical: 'mg' | 'mL' | 'mg/mL' | 'IU' | '%'

    def __repr__(self) -> str:
        return f"Quantity({self.value}{self.unit}, kind={self.kind}, raw={self.raw!r})"


# A number, optionally with decimal (accepts comma decimal e.g. "0,5").
_NUM = r"\d+(?:[.,]\d+)?"
# concentration / per-volume:  "5 mg/mL", "5 mg / 0.5 mL", "5 mg per 0.5 mL"
_CONC_RE = re.compile(
    rf"(?P<num>{_NUM})\s*(?P<numu>mg|mcg|ug|µg|g|ng)\s*(?:/|per)\s*"
    rf"(?P<den>{_NUM})?\s*(?P<denu>ml|millilitre|milliliter|l)\b",
    re.IGNORECASE,
)
# plain mass:  "5 mg", "5.0 MG", "100mcg"
_MASS_RE = re.compile(rf"(?P<num>{_NUM})\s*(?P<u>mg|mcg|ug|µg|ng|g|milligrams?|micrograms?|grams?)\b", re.IGNORECASE)
# plain volume:  "2.5 mL", "0,5 ml", "5 mL"
_VOL_RE = re.compile(rf"(?P<num>{_NUM})\s*(?P<u>ml|millilitres?|milliliters?|l|litres?|liters?)\b", re.IGNORECASE)
# activity concentration:  "100 units/mL", "100 IU / mL"  (must precede _ACT_RE)
_ACT_CONC_RE = re.compile(
    rf"(?P<num>{_NUM})\s*(?P<numu>iu|units?|u)\s*(?:/|per)\s*"
    rf"(?P<den>{_NUM})?\s*(?P<denu>ml|millilitre|milliliter|l)\b",
    re.IGNORECASE,
)
# activity:  "100 IU", "10 units"
_ACT_RE = re.compile(rf"(?P<num>{_NUM})\s*(?P<u>iu|units?|u)\b", re.IGNORECASE)
# percent:  "0.5%"
_PCT_RE = re.compile(rf"(?P<num>{_NUM})\s*%")


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _extract_quantities(text: str) -> tuple[list[Quantity], str]:
    """Pull every typed quantity out of `text`; return (quantities, remainder).

    Order matters: concentration (X unit / Y unit) is matched first so its '/'
    is not mistaken for a combination separator or a bare mass/volume.
    """
    quantities: list[Quantity] = []
    remainder = text

    def _consume(rx, builder):
        nonlocal remainder
        spans = []
        for m in rx.finditer(remainder):
            q = builder(m)
            if q is not None:
                quantities.append(q)
                spans.append((m.start(), m.end()))
        # blank out matched spans so later regexes don't re-match them
        if spans:
            chars = list(remainder)
            for s, e in spans:
                for i in range(s, e):
                    chars[i] = " "
            remainder = "".join(chars)

    def _conc(m):
        num = _to_float(m.group("num"))
        den = _to_float(m.group("den")) if m.group("den") else 1.0
        numu = m.group("numu").lower()
        mg = (num * _MASS_TO_MG.get(numu, 1.0)) if num is not None else None
        val = (mg / den) if (mg is not None and den) else None
        return Quantity(raw=m.group(0).strip(), kind="concentration",
                        value=round(val, 6) if val is not None else None, unit="mg/mL")

    def _mass(m):
        num = _to_float(m.group("num"))
        u = m.group("u").lower()
        val = num * _MASS_TO_MG.get(u, 1.0) if num is not None else None
        return Quantity(raw=m.group(0).strip(), kind="strength", value=val, unit="mg")

    def _vol(m):
        num = _to_float(m.group("num"))
        u = m.group("u").lower()
        val = num * _VOL_TO_ML.get(u, 1.0) if num is not None else None
        return Quantity(raw=m.group(0).strip(), kind="volume", value=val, unit="mL")

    def _act_conc(m):
        num = _to_float(m.group("num"))
        den = _to_float(m.group("den")) if m.group("den") else 1.0
        val = (num / den) if (num is not None and den) else None
        return Quantity(raw=m.group(0).strip(), kind="concentration",
                        value=round(val, 6) if val is not None else None, unit="IU/mL")

    def _act(m):
        return Quantity(raw=m.group(0).strip(), kind="activity",
                        value=_to_float(m.group("num")), unit="IU")

    def _pct(m):
        return Quantity(raw=m.group(0).strip(), kind="percent",
                        value=_to_float(m.group("num")), unit="%")

    _consume(_CONC_RE, _conc)       # mass concentration, must precede mass/volume
    _consume(_ACT_CONC_RE, _act_conc)  # activity concentration, must precede _ACT_RE
    _consume(_MASS_RE, _mass)
    _consume(_VOL_RE, _vol)
    _consume(_ACT_RE, _act)
    _consume(_PCT_RE, _pct)
    return quantities, remainder


def _word_strength(text: str) -> Optional[Quantity]:
    """Handle 'five milligrams' style mentions."""
    m = re.search(r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+(milligrams?|micrograms?|grams?)\b", text, re.IGNORECASE)
    if not m:
        return None
    val = _NUMBER_WORDS[m.group(1).lower()]
    unit = m.group(2).lower()
    scale = 1.0 if unit.startswith("milli") else (0.001 if unit.startswith("micro") else 1000.0)
    return Quantity(raw=m.group(0), kind="strength", value=val * scale, unit="mg")


# ============================================================
# DrugMention — the parser output
# ============================================================

@dataclass
class DrugMention:
    original_text: str
    normalized_text: str
    substance: str
    components: list[str]
    is_combination: bool
    brand: Optional[str] = None
    brand_maps_to: Optional[str] = None
    formulation: Optional[str] = None
    route: Optional[str] = None
    route_inferred: bool = False
    strength: Optional[Quantity] = None
    concentration: Optional[Quantity] = None
    volume: Optional[Quantity] = None
    other_quantities: list[Quantity] = field(default_factory=list)
    release: Optional[str] = None
    salt_tokens: list[str] = field(default_factory=list)
    regimen_flags: list[str] = field(default_factory=list)
    context_flags: list[str] = field(default_factory=list)

    def present_attributes(self) -> set[str]:
        """Which identity attributes this mention actually specifies."""
        present = set()
        if self.substance:
            present.add("substance")
        if self.is_combination:
            present.add("combination")
        if self.formulation:
            present.add("formulation")
        if self.route and not self.route_inferred:
            present.add("route")
        if self.strength:
            present.add("strength")
        if self.concentration:
            present.add("concentration")
        if self.volume:
            present.add("volume")
        if self.brand:
            present.add("brand")
        return present


def parse_drug_mention(text: str, lexicon: DrugLexicon = DEFAULT_LEXICON) -> DrugMention:
    """Parse a raw drug mention into typed, preserved attributes. Pure."""
    original = (text or "").strip()
    work = original.lower()

    # 1. Regimen / context phrases (multi-word first, longest-match) — removed so
    #    they cannot leak into the substance string.
    regimen_flags: list[str] = []
    for phrase in sorted(lexicon.regimen, key=len, reverse=True):
        if re.search(r"\b" + re.escape(phrase) + r"\b", work):
            tag = lexicon.regimen[phrase]
            if tag not in regimen_flags:
                regimen_flags.append(tag)
            work = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", work)
    context_flags: list[str] = []
    for phrase in sorted(lexicon.context, key=len, reverse=True):
        if re.search(r"\b" + re.escape(phrase) + r"\b", work):
            tag = lexicon.context[phrase]
            if tag not in context_flags:
                context_flags.append(tag)
            work = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", work)

    # 2. Quantities (typed) — extracted before anything else splits on '/'.
    quantities, work = _extract_quantities(work)
    wq = _word_strength(work)
    if wq:
        quantities.append(wq)
        work = re.sub(r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+(milligrams?|micrograms?|grams?)\b", " ", work, flags=re.IGNORECASE)

    strength = next((q for q in quantities if q.kind == "strength"), None)
    concentration = next((q for q in quantities if q.kind == "concentration"), None)
    volume = next((q for q in quantities if q.kind == "volume"), None)
    other = [q for q in quantities if q not in (strength, concentration, volume)]

    # 3. Release qualifiers, salt tokens, formulation, route (token scan).
    release = None
    for rel in sorted(lexicon.release_qualifiers, key=len, reverse=True):
        if re.search(r"\b" + re.escape(rel) + r"\b", work):
            release = rel
            work = re.sub(r"\b" + re.escape(rel) + r"\b", " ", work)
            break

    salt_tokens: list[str] = []
    formulation: Optional[str] = None
    route: Optional[str] = None
    kept_tokens: list[str] = []
    for tok in re.split(r"[\s,;]+", work):
        t = tok.strip(".,;:()[]").lower()
        if not t:
            continue
        if t in lexicon.salt_tokens:
            salt_tokens.append(t)
            continue
        if t in lexicon.formulations and formulation is None:
            formulation = t
            continue
        if t in lexicon.routes and route is None:
            route = t
            continue
        kept_tokens.append(tok.strip(".,;:").strip())

    route_inferred = False
    if route is None and formulation in lexicon.formulation_route_hint:
        route = lexicon.formulation_route_hint[formulation]
        route_inferred = True

    # 4. Substance string = what survives; split into components if a combo.
    substance_str = " ".join(t for t in kept_tokens if t).strip()
    substance_str = re.sub(r"\s+", " ", substance_str).strip(" /+-&")

    raw_components = [c.strip(" /+-&") for c in _COMBO_SPLIT_RE.split(substance_str) if c.strip(" /+-&")]
    components = [c for c in raw_components if len(c) >= 2]
    is_combination = len(components) > 1

    # 5. Brand mapping (lexicon-driven; no guessing).
    brand = None
    brand_maps_to = None
    low_substance = substance_str.lower()
    for b, generic in lexicon.brands.items():
        if re.search(r"\b" + re.escape(b.lower()) + r"\b", low_substance):
            brand = b
            brand_maps_to = generic
            break

    return DrugMention(
        original_text=original,
        normalized_text=substance_str,
        substance=substance_str,
        components=components or ([substance_str] if substance_str else []),
        is_combination=is_combination,
        brand=brand,
        brand_maps_to=brand_maps_to,
        formulation=formulation,
        route=route,
        route_inferred=route_inferred,
        strength=strength,
        concentration=concentration,
        volume=volume,
        other_quantities=other,
        release=release,
        salt_tokens=salt_tokens,
        regimen_flags=regimen_flags,
        context_flags=context_flags,
    )
