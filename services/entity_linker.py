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
# Note: "cent" is a prefix (matches center/centre/central) — do NOT anchor a
# trailing \b after it, or "cancer center" would slip through.
_EXCLUDE_COMPANY_RE = re.compile(
    r"\bhospital|\buniversit|\bcollege|\bclinic\b|clinical\s+cent|"
    r"\binstitut|\bfoundation|\bministry|\bnhs\b|national\s+institut|study\s+group|"
    r"medical\s+cent|medical\s+supply|health\s+(?:system|service|network|authorit)|"
    r"department\s+of|school\s+of|\bmilitary|\barmy\b|\bnavy\b|\bgovernment|"
    r"research\s+cent|cancer\s+cent|cancer\s+institut|oncology\s+group|"
    r"\bacademy|\bconsortium|\bregistry|center\s+of|centre\s+of|"
    # research networks / professional bodies / care sites / named individuals —
    # surfaced as prod gazetteer pollution by the relink precision probe.
    r"research\s+network|prevention\s+cent|\bphysician|\bsociety\b|"
    r"cancer\s+research|\bcollaboration\b|\bassociation\b|cardiology|psychiatric|"
    r"\bMD\b|\bPhD\b|prevention\s+research",
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
    # generic-word company rows that matched real headlines in the prod probe
    "response", "leading", "active", "products", "medicines", "medication",
    "msn", "met", "intervention", "control", "network", "products",
}

# Non-drug rows that exist in the drugs table as data errors / generic phrases.
# A name is excluded only when its WHOLE normalized form equals one of these,
# so real drugs ("insulin glargine") are unaffected by a class term ("insulin").
_DRUG_STOPLIST = {
    "weight loss", "obesity", "placebo", "saline", "diabetes", "control",
    "standard of care", "vehicle", "comparator", "best supportive care",
    "weight management", "lifestyle", "diet", "exercise",
    # drug-class labels and trial-arm rows the prod probe mis-matched as drugs
    "glp 1", "glp1", "medication", "met", "active control", "intervention",
    "insulin", "sglt2", "soc", "active comparator", "study drug",
}


def _normalize(text: str) -> str:
    # Collapse to single spaces so index keys match the n-gram lookups in
    # link() (which join tokens with single spaces).
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in _normalize(text).split() if t]


# ── Priority allowlist (strategy-doc input #1: the GLP-1 field) ──────
# In priority_only mode the gazetteer is built ONLY from these entities
# (resolved against the DB), giving high precision on a polluted companies
# table. Edit this list to expand the competitor universe.
_PRIORITY_COMPANIES = [
    "Eli Lilly", "Novo Nordisk", "Pfizer", "Amgen", "Merck", "AstraZeneca",
    "Roche", "Sanofi", "Boehringer Ingelheim", "Viking Therapeutics",
    "Structure Therapeutics", "Novartis", "AbbVie", "Bristol Myers Squibb",
    "Johnson & Johnson", "Zealand Pharma", "Altimmune", "Gilead",
]
# alias → which priority company it denotes
_PRIORITY_COMPANY_ALIASES = {
    "lilly": "Eli Lilly", "novo": "Novo Nordisk", "bms": "Bristol Myers Squibb",
    "jnj": "Johnson & Johnson", "j&j": "Johnson & Johnson", "bi": "Boehringer Ingelheim",
    "az": "AstraZeneca", "gsk": "GSK", "abbvie": "AbbVie",
}
_PRIORITY_DRUGS = [
    "semaglutide", "tirzepatide", "orforglipron", "retatrutide", "survodutide",
    "danuglipron", "cagrilintide", "cagrisema", "ecnoglutide", "pemvidutide",
    "mazdutide", "maritide", "Wegovy", "Ozempic", "Rybelsus", "Zepbound",
    "Mounjaro", "Saxenda", "Victoza", "Trulicity",
]


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
    _CONF_FULL = 0.9            # full canonical name appeared
    _CONF_PRIORITY_ALIAS = 0.85  # a hand-vetted short-form (bms, jnj…) appeared
    _CONF_ALIAS = 0.72         # a distinctive auto-generated short-form token appeared

    def __init__(self, db):
        self.db = db
        # normalized phrase -> (entity_type, entity_id, canonical_name, is_full)
        self._index: dict[str, tuple[str, str, str, bool]] = {}
        # phrases that are hand-vetted priority short-forms — trusted above
        # ordinary auto-aliases so a precision-first backfill can accept them.
        self._priority_alias_phrases: set[str] = set()
        self._loaded = False
        self._priority_only = False

    # ── build ──────────────────────────────────────────────────────
    def load(
        self, priority_only: bool = False, with_priority_aliases: bool = False
    ) -> "EntityLinker":
        """Build the gazetteer.

        priority_only        — only the ~18 curated GLP-1 entities (highest
                               precision, lowest recall).
        with_priority_aliases — full company/drug universe PLUS the curated
                               short-form initialisms (bms, jnj…) the full
                               gazetteer's 4-char token rule would drop. This is
                               the mode the signal promoter uses: broad recall,
                               with the hand-vetted aliases kept high-confidence.
        """
        self._index = {}
        self._priority_alias_phrases = set()
        self._priority_only = priority_only
        if priority_only:
            self._load_priority()
        else:
            self._load_companies()
            self._load_drugs()
            if with_priority_aliases:
                self._load_priority_aliases()
        self._loaded = True
        logger.info(
            "entity linker: indexed %d phrases (priority_only=%s, priority_aliases=%s)",
            len(self._index), priority_only, with_priority_aliases,
        )
        return self

    def _find_company(self, name: str) -> dict | None:
        """Best DB company row for a priority name: exact, else shortest ILIKE
        (avoids headline-fragment rows that merely contain the name)."""
        try:
            rows = self.db.fetch_all(
                "SELECT id, name FROM companies WHERE name ILIKE %s ORDER BY length(name) LIMIT 5",
                [f"%{name}%"],
            )
        except Exception:
            return None
        nl = name.lower()
        exact = [r for r in rows if (r.get("name") or "").lower() == nl]
        pick = exact[0] if exact else (rows[0] if rows else None)
        if pick and not _looks_like_sentence(pick.get("name") or ""):
            return pick
        return None

    def _find_drug(self, name: str) -> dict | None:
        try:
            rows = self.db.fetch_all(
                """SELECT id, generic_name, brand_name FROM drugs
                    WHERE generic_name ILIKE %s OR brand_name ILIKE %s
                    ORDER BY length(coalesce(generic_name, brand_name)) LIMIT 3""",
                [name, name],
            )
        except Exception:
            rows = []
        return rows[0] if rows else None

    def _load_priority(self) -> None:
        # Companies + their canonical name as the display name.
        canon: dict[str, dict] = {}
        for pname in _PRIORITY_COMPANIES:
            row = self._find_company(pname)
            if not row:
                continue
            canon[pname] = row
            self._add(pname, "company", row["id"], pname, True)
            for tok in _tokens(pname):
                if tok in _SUFFIX_TOKENS or tok in _ALIAS_STOPWORDS or len(tok) < _MIN_TOKEN_LEN:
                    continue
                self._add(tok, "company", row["id"], pname, False)
        for alias, target in _PRIORITY_COMPANY_ALIASES.items():
            row = canon.get(target) or self._find_company(target)
            if row:
                self._add(alias, "company", row["id"], target, False)
        # Drugs (generic + brand → generic canonical).
        for dname in _PRIORITY_DRUGS:
            row = self._find_drug(dname)
            if not row:
                continue
            canonical = row.get("generic_name") or row.get("brand_name") or dname
            self._add(dname, "drug", row["id"], canonical, True)

    def _add(self, phrase: str, etype: str, eid: str, cname: str, is_full: bool) -> None:
        norm = _normalize(phrase)
        if len(norm) < _MIN_NAME_LEN:
            return
        # A single-token name that is a generic English/industry word (e.g. a
        # company row literally named "center"/"MSN" or a drug row "Medication")
        # is a data-quality artifact, not an entity — never index it, even as a
        # full name. Multi-token names ("Jazz Pharmaceuticals") are unaffected,
        # and distinctive single tokens ("incyte", "jazz") aren't in the set.
        if " " not in norm and norm in _ALIAS_STOPWORDS:
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

    def _load_priority_aliases(self) -> None:
        """Overlay the curated company short-forms (bms, jnj, lilly…) on top of
        the full gazetteer.

        The full loader drops initialisms (<4 chars) and most short-forms via
        the token rules, so "bms acquires…" or "Lilly pens…" would only land on
        the polluted-table auto-alias (or nothing). These hand-vetted forms are
        marked as priority aliases (higher confidence) so a precision-first
        backfill trusts them without trusting every auto-generated token.
        """
        canon: dict[str, dict] = {}
        for pname in _PRIORITY_COMPANIES:
            row = self._find_company(pname)
            if row:
                canon[pname] = row
        for alias, target in _PRIORITY_COMPANY_ALIASES.items():
            row = canon.get(target) or self._find_company(target)
            if not row:
                continue
            norm = _normalize(alias)
            if len(norm) < _MIN_NAME_LEN:
                continue  # too short/ambiguous to index safely (e.g. "az", "bi")
            # Priority aliases win the phrase outright (overwrite any auto-alias)
            # and are tracked so link() can grade them above ordinary aliases.
            self._index[norm] = ("company", str(row["id"]), target, False)
            self._priority_alias_phrases.add(norm)

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
        if is_full:
            confidence = self._CONF_FULL
        elif phrase in self._priority_alias_phrases:
            confidence = self._CONF_PRIORITY_ALIAS
        else:
            confidence = self._CONF_ALIAS
        return LinkResult(
            entity_type=etype,
            entity_id=eid,
            canonical_name=cname,
            confidence=confidence,
            matched_text=phrase,
        )
