"""Modality classifier — generic_name + mechanism → modality enum value.

SPEC-016 §7 swimlane A1.2. Used by:
  - The data steward when backfilling modality on existing drugs
  - Connectors during ingest of new drugs (call before INSERT)
  - The 8-K parser when extracting deals — the deal_subject can be
    a "phase 2 ADC for HER2-positive solid tumors" and we want to
    tag the modality even before the asset is in our drugs table

Heuristic-only — no LLM. The classifier is intentionally conservative:
when uncertain, returns 'other' (always a valid CHECK enum value), never
None. Gives the steward / human a clean value to override.

To extend: add a row to MODALITY_RULES in priority order. Earlier rules
win. The 'other' rule is the fallback and must remain last.
"""

from __future__ import annotations

import re
from typing import Final


# ────────────────────────────────────────────────────────────────────
# Enum values — must match the CHECK constraint in migration 038
# ────────────────────────────────────────────────────────────────────

MODALITY_VALUES: Final[frozenset[str]] = frozenset({
    "small_molecule",
    "mab",
    "adc",
    "bispecific",
    "gene_therapy",
    "cell_therapy",
    "rna",
    "vaccine",
    "device",
    "other",
})


# ────────────────────────────────────────────────────────────────────
# Heuristic rules — order matters; first match wins
# ────────────────────────────────────────────────────────────────────

# Each rule: (description, predicate(generic_lower, mechanism_lower) → bool, modality)

def _has(s: str | None, *needles: str) -> bool:
    if not s:
        return False
    s = s.lower()
    return any(n in s for n in needles)


def _suffix(generic: str | None, *suffixes: str) -> bool:
    if not generic:
        return False
    g = generic.lower()
    return any(g.endswith(s) for s in suffixes)


def _word(s: str | None, *words: str) -> bool:
    if not s:
        return False
    return any(re.search(rf"\b{re.escape(w)}\b", s, re.IGNORECASE) for w in words)


# Rule signature: (name, predicate, output)
_Rule = tuple[str, "callable", str]

MODALITY_RULES: list[_Rule] = [
    # ── Vaccines (mRNA + traditional). Check first because
    #    `tozinameran` matches both "rna" suffix and vaccine semantics.
    (
        "vaccine_explicit",
        lambda g, m: _word(m, "vaccine", "vaccination", "immunisation", "immunization"),
        "vaccine",
    ),
    (
        "vaccine_mrna_in_mech",
        lambda g, m: _has(m, "mrna encoding") or _has(m, "mrna-based"),
        "vaccine",
    ),

    # ── Antibody-drug conjugates (suffix recognition)
    #    -mab + emtansine / -tecan / -vedotin / -pasudotox / -sirvedotin
    (
        "adc_compound_suffix",
        lambda g, m: bool(g) and (
            "antibody-drug conjugate" in (m or "")
            or any(part in (g or "").lower() for part in (
                "emtansine", "vedotin", "deruxtecan", "tesirine",
                "pasudotox", "ozogamicin", "sirvedotin",
            ))
        ),
        "adc",
    ),

    # ── Bispecifics (BiTE, biTE, T-cell-engagers)
    (
        "bispecific",
        lambda g, m: (
            _has(m, "bispecific", "bite", "x cd3", "× cd3", "dart")
            or _suffix(g, "tamab")  # bispecific INN suffix per WHO
        ),
        "bispecific",
    ),

    # ── CAR-T / cell therapies (suffix -leucel, -aleucel; or "car-t")
    (
        "cell_therapy",
        lambda g, m: (
            _suffix(g, "leucel", "aleucel")
            or _has(m, "car-t", "car t", "tcr-t", "nk-cell", "tils",
                    "tumour-infiltrating", "tumor-infiltrating",
                    "chimeric antigen receptor")
        ),
        "cell_therapy",
    ),

    # ── Gene therapy (AAV/lentiviral vectors, suffix -nogene -parvovec)
    (
        "gene_therapy",
        lambda g, m: (
            _suffix(g, "parvovec", "nogene", "parvovec.")
            or _has(m, "aav", "adeno-associated", "lentiviral",
                    "gene therapy", "in-vivo gene")
        ),
        "gene_therapy",
    ),

    # ── RNA therapeutics (siRNA, ASO, mRNA therapeutics — NOT vaccines,
    #    those are caught earlier)
    (
        "rna_therapeutic",
        lambda g, m: (
            _has(m, "small interfering rna", "sirna", "antisense oligonucleotide",
                 "antisense", "morpholino")
            or _suffix(g, "siran", "rsen", "mersen")
        ),
        "rna",
    ),

    # ── mAbs (suffix -mab). Check AFTER ADCs/bispecifics so they
    #    take precedence on compound names.
    (
        "monoclonal_antibody",
        lambda g, m: _suffix(g, "mab") or _has(m, "monoclonal antibody"),
        "mab",
    ),

    # ── Devices (rare in pharma but exists)
    (
        "device",
        lambda g, m: _has(m, "drug-eluting stent", "infusion pump", "device-led"),
        "device",
    ),

    # ── Small molecules — broad fallback before 'other'.
    #    Strong signals: -ib, -tinib, -afenib, -pril, -sartan, -statin, etc.,
    #    plus generic descriptors in mechanism.
    (
        "small_molecule_suffix",
        lambda g, m: _suffix(
            g,
            "tinib", "ib", "afenib", "pril", "sartan", "statin", "olol",
            "azole", "cycline", "mycin", "floxacin", "prazole", "zumab",  # -zumab is mab caught earlier
            "azepine", "vir", "navir",
        ),
        "small_molecule",
    ),
    (
        "small_molecule_mechanism",
        lambda g, m: _has(
            m,
            "kinase inhibitor", "ion channel", "receptor antagonist",
            "agonist", "small molecule", "biguanide", "sglt", "dpp-",
            "statin", "ace inhibitor", "beta blocker", "calcium channel",
        ),
        "small_molecule",
    ),
]


def classify_modality(
    generic_name: str | None,
    mechanism: str | None,
) -> str:
    """Classify a drug into one of the MODALITY_VALUES.

    Returns 'other' as fallback — never None and never an invalid value.
    Safe to call with None/empty inputs.
    """
    g = (generic_name or "").strip()
    m = (mechanism or "").strip()

    if not g and not m:
        return "other"

    for _name, predicate, output in MODALITY_RULES:
        try:
            if predicate(g, m):
                # Defence-in-depth: enum membership check
                if output in MODALITY_VALUES:
                    return output
        except Exception:
            # A bad predicate must not crash the classifier
            continue

    return "other"
