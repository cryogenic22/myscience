"""
Pharma-specific mention normalizers.

Cleans drug and company names before entity resolution to reduce
false duplicates (e.g., 49 semaglutide records from dosage variants).

Drug: "SEMAGLUTIDE 0.5 MG INJECTION" → "semaglutide"
Company: "Novo Nordisk A/S, Inc." → "novo nordisk"
"""

from __future__ import annotations

import re


# Dosage forms, routes, strengths — stripped from drug mentions
_DOSAGE_FORMS = {
    "tablet", "tablets", "capsule", "capsules", "injection", "injectable",
    "solution", "suspension", "cream", "ointment", "gel", "patch", "patches",
    "inhaler", "inhalation", "spray", "drops", "suppository", "powder",
    "granules", "syrup", "elixir", "emulsion", "lotion", "foam", "implant",
    "pen", "prefilled", "pre-filled", "autoinjector", "auto-injector",
    "vial", "ampoule", "infusion", "ophthalmic", "nasal", "oral",
    "subcutaneous", "intramuscular", "intravenous", "topical", "rectal",
    "extended-release", "extended release", "delayed-release", "delayed release",
    "immediate-release", "er", "xr", "sr", "cr", "dr", "ir", "hfa",
    "mdi", "dpi", "sublingual", "buccal", "transdermal",
}

# Strength patterns: "0.5mg", "10 mg/ml", "100mcg", etc.
_STRENGTH_RE = re.compile(
    r'\b\d+(?:\.\d+)?\s*(?:mg|mcg|ug|g|ml|l|iu|units?|meq|mmol|%)'
    r'(?:\s*/\s*\d*(?:\.\d+)?\s*(?:mg|mcg|ug|g|ml|l|hr|day|dose|actuation))?',
    re.IGNORECASE,
)

# Combination separator patterns
_COMBO_SEP_RE = re.compile(r'\s*/\s*|\s+and\s+|\s+&\s+', re.IGNORECASE)

# Company suffixes
_COMPANY_SUFFIXES = {
    "inc", "inc.", "incorporated", "corp", "corp.", "corporation",
    "ltd", "ltd.", "limited", "llc", "l.l.c.", "plc", "p.l.c.",
    "and", "of", "the",
    "co", "co.", "company", "gmbh", "ag", "sa", "s.a.", "nv", "n.v.",
    "bv", "b.v.", "ab", "a/s", "pty", "pvt", "holdings", "group",
    "pharmaceuticals", "pharmaceutical", "pharma", "therapeutics",
    "biosciences", "bioscience", "biotech", "biotechnology",
    "laboratories", "laboratory", "labs", "sciences", "medical",
}

# Non-drug terms that should be excluded
DRUG_SKIP_TERMS = {
    "placebo", "standard of care", "usual care", "sham", "no intervention",
    "behavioral", "dietary supplement", "device", "procedure", "other",
    "standard care", "best supportive care", "observation", "watchful waiting",
    "lifestyle modification", "diet", "exercise", "counseling",
    "physical therapy", "occupational therapy", "radiation",
    "surgery", "surgical", "comparator", "active comparator",
}

COMPANY_SKIP_TERMS = {
    "individual", "other", "unknown", "not available", "n/a",
}


def normalize_drug_mention(raw: str) -> str:
    """
    Extract the base compound name from a drug mention string.

    "SEMAGLUTIDE 0.5 MG INJECTION" → "semaglutide"
    "Metformin HCl Extended Release 500mg" → "metformin hcl"
    "Drug: Empagliflozin" → "empagliflozin"
    """
    text = raw.strip()
    if not text:
        return text

    # Remove common prefixes
    for prefix in ("Drug:", "drug:", "DRUG:", "Active Comparator:", "Experimental:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Remove bracketed content like (brand name) or [dosage]
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]', ' ', text)

    # Remove strength patterns
    text = _STRENGTH_RE.sub(' ', text)

    # Remove multi-word dosage form phrases before tokenization
    for phrase in ("extended release", "extended-release", "delayed release",
                   "delayed-release", "immediate release", "immediate-release",
                   "modified release", "controlled release", "sustained release",
                   "long acting", "long-acting", "once weekly", "once daily"):
        text = text.lower().replace(phrase, ' ')

    # Remove registered/trademark symbols
    text = text.replace('\u00ae', '').replace('\u2122', '')

    # Tokenize and remove dosage form words
    tokens = text.lower().split()
    cleaned = []
    for token in tokens:
        token = token.strip('.,;:-')
        if not token:
            continue
        if token in _DOSAGE_FORMS:
            continue
        # Stop at dosage form words (everything after is usually form/route)
        cleaned.append(token)

    result = ' '.join(cleaned).strip()

    # Remove trailing punctuation
    result = result.rstrip('.,;:-')

    return result if result else raw.strip().lower()


def normalize_company_mention(raw: str) -> str:
    """
    Normalize a company name for matching.

    "Novo Nordisk A/S, Inc." → "novo nordisk"
    "Eli Lilly and Company" → "eli lilly"
    """
    text = raw.strip()
    if not text:
        return text

    text = text.lower()

    # Remove content in parentheses
    text = re.sub(r'\([^)]*\)', ' ', text)

    # Remove common punctuation
    text = text.replace(',', ' ').replace('.', ' ').replace('-', ' ')

    # Tokenize and remove company suffixes
    tokens = text.split()
    cleaned = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token in _COMPANY_SUFFIXES:
            continue
        cleaned.append(token)

    result = ' '.join(cleaned).strip()
    return result if result else raw.strip().lower()
