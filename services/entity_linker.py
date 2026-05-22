"""Loop ① — link free-text signal headlines to canonical entities.

The signal producer buckets entityless news as 'market'. The high-value
events (approvals, deals, readouts) name the company/drug in the headline
("Lilly pens $202M deal…", "Savara Presented Phase 2 data…") but carry no
structured entity link. This module mines the headline for a known entity.

Approach — a gazetteer built from the DB (companies + drugs), with
auto-generated short-form aliases (so "Lilly" matches "Eli Lilly and
Company"). Headlines are scanned by n-gram lookup; the longest, most
specific match wins. High precision for known entities — which is exactly
the priority GLP-1 field (Novo, Lilly, Wegovy, Ozempic, Zepbound…). Misses
fall back to the honest 'market' bucket.

Deterministic, no LLM. Reuses DB entity tables rather than re-deriving.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Corporate suffixes / connective tokens stripped when generating aliases.
_SUFFIX_TOKENS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "plc", "ag", "sa", "nv", "as", "a/s", "se", "gmbh",
    "holdings", "group", "and", "the", "pharmaceuticals", "pharmaceutical",
    "pharma", "therapeutics", "biosciences", "bioscience", "biopharma",
    "sciences", "laboratories", "labs",
}
_MIN_TOKEN_LEN = 4          # don't index short/ambiguous tokens ("eli", "ro")
_MIN_NAME_LEN = 3
_MAX_NGRAM = 4              # scan up to 4-word phrases

# The companies table is polluted with trial sponsors / hospitals / study
# groups / agencies (from ClinicalTrials.gov ingestion). These are not the
# strategic competitors a CI user cares about and wreck linker precision
# ("The Harvard Drug Group", "TIMI Study Group"). Exclude by org-type keyword.
_EXCLUDE_COMPANY_RE = re.compile(
    r"\b(hospital|hospitals|university|universities|college|clinic|clinical\s+cent|"
    r"institute|institutes|foundation|ministry|nhs|national\s+institut|study\s+group|"
    r"medical\s+cent|medical\s+supply|health\s+(system|service|services|network|authority)|"
    r"department\s+of|school\s+of|board|council|authority|affiliated|military|"
    r"army|navy|government|trust|research\s+cent|cancer\s+cent|cancer\s+inst|"
    r"oncology\s+group|academy|administration|consortium|network|registry|"
    r"society|association|center\s+of|centre\s+of)\b",
    re.IGNORECASE,
)

# A real company name is short and noun-like. Headline fragments leaked into
# the companies table ("Pfizer's Upjohn has merged with…") — drop anything
# that reads like a sentence: too many words, or containing verbs/possessives.
_MAX_COMPANY_WORDS = 6
_SENTENCE_MARKERS = (" has ", " have ", " with ", " for ", " to ", " and the ",
                     " merged ", " acquires ", " announces ", "'s ", " its ")


def _looks_like_sentence(name: str) -> bool:
    n = (name or "").lower()
    if len(name.split()) > _MAX_COMPANY_WORDS:
        return True
    return any(m in f" {n} " for m in _SENTENCE_MARKERS)

# Generic industry/English words that must NOT become company short-form
# aliases (otherwise "a new drug" matches "The Harvard Drug Group").
_ALIAS_STOPWORDS = {
    "drug", "drugs", "group", "health", "care", "medical", "life", "global",
    "data", "study", "clinical", "center", "centre", "research", "national",
    "american", "european", "international", "therapy", "world", "united",
    "general", "royal", "federal", "partners", "ventures", "capital",
    "systems", "solutions", "technologies", "digital", "biotech", "medicine",
    "first", "new", "gen", "bio", "labs", "holdings", "people", "company",
}

# Non-drug rows that exist in the drugs table as data errors / generic phrases.
_DRUG_STOPLIST = {
    "weight loss", "obesity", "placebo", "saline", "diabetes", "control",
    "standard of care", "vehicle", "comparator", "best supportive care",
    "weight management", "lifestyle", "diet", "exercise",
}


def _normalize(text: str) -> str:
    # Collapse to single spaces so index keys match the n-gram lookups in
    # link() (which join tokens with single spaces).
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _normalize(text).split() if t]


@dataclass
class LinkResult:
    entity_type: str
    entity_id: str
    canonical_name: str
    confidence: float
    matched_text: str


class EntityLinker:
    """Gazetteer linker. Call load() once, then link(headline) per signal."""

    # confidence by how the name was matched
    _CONF_FULL = 0.9        # full canonical name appeared
    _CONF_ALIAS = 0.72      # a distinctive short-form token appeared

    def __init__(self, db):
        self.db = db
        # normalized phrase -> (entity_type, entity_id, canonical_name, is_full)
        self._index: dict[str, tuple[str, str, str, bool]] = {}
        self._loaded = False

    # ── build ──────────────────────────────────────────────────────
    def load(self) -> "EntityLinker":
        self._index = {}
        self._load_companies()
        self._load_drugs()
        self._loaded = True
        logger.info("entity linker: indexed %d phrases", len(self._index))
        return self

    def _add(self, phrase: str, etype: str, eid: str, cname: str, is_full: bool) -> None:
        norm = _normalize(phrase)
        if len(norm) < _MIN_NAME_LEN:
            return
        # Full-name entries win over alias entries for the same phrase.
        existing = self._index.get(norm)
        if existing is None or (is_full and not existing[3]):
            self._index[norm] = (etype, str(eid), cname, is_full)

    def _load_companies(self) -> None:
        try:
            rows = self.db.fetch_all(
                "SELECT id, name FROM companies WHERE name IS NOT NULL", []
            )
        except Exception:
            logger.exception("entity linker: companies query failed")
            rows = []
        skipped = 0
        for r in rows:
            name = r.get("name") or ""
            if _EXCLUDE_COMPANY_RE.search(name) or _looks_like_sentence(name):
                skipped += 1
                continue  # trial site / agency / headline fragment — not a competitor
            self._add(name, "company", r["id"], name, True)
            # auto short-form aliases: distinctive tokens, suffixes stripped
            for tok in _tokens(name):
                if (tok in _SUFFIX_TOKENS or tok in _ALIAS_STOPWORDS
                        or len(tok) < _MIN_TOKEN_LEN):
                    continue
                self._add(tok, "company", r["id"], name, False)
        if skipped:
            logger.info("entity linker: excluded %d non-competitor companies", skipped)

    def _load_drugs(self) -> None:
        try:
            rows = self.db.fetch_all(
                "SELECT id, generic_name, brand_name FROM drugs", []
            )
        except Exception:
            logger.exception("entity linker: drugs query failed")
            rows = []
        for r in rows:
            generic = r.get("generic_name") or ""
            brand = r.get("brand_name") or ""
            canonical = generic or brand
            if not canonical:
                continue
            if generic and _normalize(generic) not in _DRUG_STOPLIST:
                self._add(generic, "drug", r["id"], canonical, True)
            if brand and _normalize(brand) not in _DRUG_STOPLIST:
                self._add(brand, "drug", r["id"], canonical, True)

    # ── link ───────────────────────────────────────────────────────
    def link(self, text: str) -> LinkResult | None:
        """Return the best canonical entity mentioned in `text`, or None.

        Longest matching phrase wins (most specific). Drugs are preferred
        over companies at equal length (a named drug is more specific than
        the company that makes it). Full-name matches beat alias matches.
        """
        if not self._loaded:
            self.load()
        toks = _tokens(text)
        if not toks:
            return None

        best: tuple[int, int, int, str] | None = None  # (ngram_len, is_full, type_rank, phrase)
        for i in range(len(toks)):
            for n in range(min(_MAX_NGRAM, len(toks) - i), 0, -1):
                phrase = " ".join(toks[i:i + n])
                hit = self._index.get(phrase)
                if not hit:
                    continue
                etype, _eid, _cn, is_full = hit
                type_rank = 1 if etype == "drug" else 0
                key = (n, 1 if is_full else 0, type_rank, phrase)
                if best is None or key > best:
                    best = key

        if best is None:
            return None
        phrase = best[3]
        etype, eid, cname, is_full = self._index[phrase]
        return LinkResult(
            entity_type=etype,
            entity_id=eid,
            canonical_name=cname,
            confidence=self._CONF_FULL if is_full else self._CONF_ALIAS,
            matched_text=phrase,
        )
