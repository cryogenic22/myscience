"""Person role-classification + history helpers.

SPEC-016 §7 swimlane A1.4. Used by:
  - The A2.1 8-K Item 5.02 parser — calls build_role_entry() with extracted
    title, classifies seniority + functional area, appends to roles_history
  - The pattern detector (B5) — reads roles_history and emits
    "exec exodus" pattern_signal when N transitions hit one company in W days
  - The entity_resolver fuzzy cascade — reads canonical_name for person matching

Pure functions, no DB I/O. Conservative classifiers — when uncertain,
fall back to 'Other' / 'other' (always a valid output).
"""

from __future__ import annotations

import re
import unicodedata
from typing import TypedDict, Literal


SeniorityTier = Literal["C-suite", "EVP/SVP", "VP", "Director", "Other"]
FunctionalArea = Literal[
    "CEO", "CFO", "CSO", "CMO", "CCO",
    "head_of_RD", "board", "other",
]


SENIORITY_VALUES: frozenset[str] = frozenset({
    "C-suite", "EVP/SVP", "VP", "Director", "Other",
})

FUNCTIONAL_AREA_VALUES: frozenset[str] = frozenset({
    "CEO", "CFO", "CSO", "CMO", "CCO",
    "head_of_RD", "board", "other",
})


# ────────────────────────────────────────────────────────────────────
# Seniority classification
# ────────────────────────────────────────────────────────────────────

def classify_seniority(title: str | None) -> SeniorityTier:
    """Return one of {C-suite, EVP/SVP, VP, Director, Other}.

    Always returns a valid enum member — never None.
    """
    if not title:
        return "Other"

    t = title.lower()

    # Board roles → treat as C-suite-equivalent (per CI HR2.3 hard rule)
    if re.search(r"\bboard\b", t) or "independent director" in t or \
       re.search(r"\bchair(?:man|woman|person)?\b", t):
        return "C-suite"

    # C-suite — explicit chief titles + abbreviations
    if re.search(r"\bchief\s+\w+\s+officer\b", t):
        return "C-suite"
    if re.search(r"\b(?:ceo|cfo|cmo|cso|cco|coo|cto|cio|cpo|cdo|cco)\b", t):
        return "C-suite"

    # EVP / SVP
    if re.search(r"\b(?:executive\s+vice\s+president|evp)\b", t):
        return "EVP/SVP"
    if re.search(r"\b(?:senior\s+vice\s+president|svp)\b", t):
        return "EVP/SVP"

    # VP (after EVP/SVP — order matters)
    if re.search(r"\b(?:vice\s+president|vp)\b", t):
        return "VP"

    # Director
    if re.search(r"\bdirector\b", t):
        return "Director"

    return "Other"


# ────────────────────────────────────────────────────────────────────
# Functional area classification
# ────────────────────────────────────────────────────────────────────

def classify_functional_area(title: str | None) -> FunctionalArea:
    """Return one of {CEO, CFO, CSO, CMO, CCO, head_of_RD, board, other}."""
    if not title:
        return "other"

    t = title.lower()

    # Board first (so "board director" doesn't fall through to 'other')
    if re.search(r"\bboard\b", t) or \
       re.search(r"\b(?:independent\s+director|lead\s+director)\b", t) or \
       re.search(r"\bchair\b", t):
        return "board"

    # CEO
    if re.search(r"\bchief\s+executive\s+officer\b", t) or re.search(r"\bceo\b", t):
        return "CEO"

    # CFO
    if re.search(r"\bchief\s+financial\s+officer\b", t) or re.search(r"\bcfo\b", t):
        return "CFO"

    # CMO (medical, not marketing — context disambiguates if both match)
    if re.search(r"\bchief\s+medical\s+officer\b", t):
        return "CMO"
    if re.search(r"\bcmo\b", t) and not re.search(r"\bcommercial\b", t):
        return "CMO"

    # CSO (scientific)
    if re.search(r"\bchief\s+scientific\s+officer\b", t) or re.search(r"\bcso\b", t):
        return "CSO"

    # CCO (commercial)
    if re.search(r"\bchief\s+commercial\s+officer\b", t) or re.search(r"\bcco\b", t):
        return "CCO"

    # Head of R&D — covers EVP R&D, President R&D, Head of Research, etc.
    if re.search(r"\b(?:r\s*&\s*d|research\s+(?:and|&)\s+development|"
                 r"research\s+and\s+development|research\s+development)\b", t):
        return "head_of_RD"
    if re.search(r"\bhead\s+of\s+r\s*&\s*d\b", t):
        return "head_of_RD"

    return "other"


# ────────────────────────────────────────────────────────────────────
# Name normalisation
# ────────────────────────────────────────────────────────────────────

_HONORIFIC_RE = re.compile(
    r"(^|\s)(?:Dr|Mr|Mrs|Ms|Prof|Professor|Sir)\.?(\s|$)",
    re.IGNORECASE,
)
_DEGREE_SUFFIX_RE = re.compile(
    r",?\s+(?:Ph\.?D\.?|M\.?D\.?|MBA|J\.?D\.?|Esq\.?|D\.Sc\.?|D\.Phil\.?)$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def normalise_name(name: str | None) -> str:
    """Lowercase, accent-strip, drop honorifics + degree suffixes,
    collapse whitespace.

    Empty / None → empty string. Never raises.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    # Drop combining marks
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _HONORIFIC_RE.sub(" ", s)
    s = _DEGREE_SUFFIX_RE.sub("", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s.lower()


# ────────────────────────────────────────────────────────────────────
# Role-history entry construction
# ────────────────────────────────────────────────────────────────────

class RoleHistoryEntry(TypedDict, total=False):
    company_id: str | None
    company_name: str | None
    title: str
    functional_area: FunctionalArea
    seniority_tier: SeniorityTier
    start_date: str | None
    end_date: str | None
    transition_id: str | None
    source_document_id: str | None
    confirmed: bool


def build_role_entry(
    *,
    company_id: str | None,
    company_name: str | None,
    title: str,
    start_date: str | None,
    end_date: str | None,
    transition_id: str | None,
    source_document_id: str | None,
    confirmed: bool,
) -> RoleHistoryEntry:
    """Construct a single role entry. Classifies seniority + functional area.

    `confirmed` should be True only when the source is confidence_tier=confirmed
    (8-K Item 5.02, DEF 14A, company leadership page). LinkedIn-only entries
    must pass confirmed=False.
    """
    return {
        "company_id": company_id,
        "company_name": company_name,
        "title": title,
        "functional_area": classify_functional_area(title),
        "seniority_tier": classify_seniority(title),
        "start_date": start_date,
        "end_date": end_date,
        "transition_id": transition_id,
        "source_document_id": source_document_id,
        "confirmed": confirmed,
    }
