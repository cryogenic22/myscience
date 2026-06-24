"""
LLM Synthesis Service for Market-Zero.

Takes structured data (evidence, metrics, graph context) gathered by the
deterministic service layer and synthesizes it into analyst-grade narratives
using an LLM. Falls back to template narratives if no API key is configured
or if the LLM call fails.

Architecture rationale:
  - Deterministic services handle data gathering (fast, reliable, complete)
  - LLM handles ONLY synthesis (what it's good at: turning data into insight)
  - Single LLM call per request (~2-3s latency), not multi-step agent chains
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Post-synthesis validation ──────────────────────────────────────

_CITATION_RE = re.compile(r"\[(\d+)\]")


# Type alternation is open-ended (``[a-z_]+``) on purpose: the domain pack has 9
# entity types (drug/company/trial/mechanism/therapeutic_area/investigator +
# literature/event/patent) and the sentinel/id checks below are type-agnostic, so
# a placeholder must be stripped for ANY type — an enumerated subset let the leak
# survive on literature/event/patent links.
_ENTITY_LINK_RE = re.compile(
    r"\[([^\]]+?)\]\(/entity/([a-z_]+)/([^)]+?)\)"
)

# Example ids that appear in the synthesis prompt as worked examples. A poorly
# resolved entity gives the model no real id to copy, so it reproduces one of
# these verbatim and it renders as a fake, clickable citation (reviewer F3:
# `[Donanemab](/entity/drug/abc-123)`). These ids must NEVER survive to the
# screen, on any path, regardless of whether the caller supplies a valid-id set.
# Compared lowercased. `abc-123`/`c-456` are the legacy examples (kept here so an
# already-deployed prompt can't leak them); `example_id_do_not_copy` is the new,
# deliberately-uncopyable example the prompt now uses.
_SENTINEL_ENTITY_IDS = {"abc-123", "c-456", "example_id_do_not_copy"}


def strip_invalid_entity_links(
    narrative: str, valid_entity_ids: set[str] | None = None
) -> dict:
    """Strip ``[label](/entity/{type}/{id})`` links whose id is not trustworthy,
    keeping the plain label text (no information loss).

    A link is stripped when its id is a known prompt-example sentinel
    (``_SENTINEL_ENTITY_IDS``) OR — when ``valid_entity_ids`` is supplied — the id
    is not in that set (the entity ids actually present in this turn's evidence).
    Ids are compared case-insensitively. With no ``valid_entity_ids`` only the
    sentinels are stripped, so this is a safe both-path default that always kills
    the ``abc-123`` leak without risking a real link.

    Returns ``{"narrative": str, "stripped": int}``.
    """
    if not narrative:
        return {"narrative": narrative or "", "stripped": 0}

    valid_lower = {str(i).lower() for i in valid_entity_ids} if valid_entity_ids is not None else None
    stripped = 0

    def _replace(m: "re.Match") -> str:
        nonlocal stripped
        label, _etype, ident = m.group(1), m.group(2), m.group(3)
        low = ident.strip().lower()
        bad = low in _SENTINEL_ENTITY_IDS or (valid_lower is not None and low not in valid_lower)
        if bad:
            stripped += 1
            logger.debug("Stripped entity link with unresolved id %r (label=%r)", ident, label)
            return label  # keep the entity name, drop the fake link
        return m.group(0)

    cleaned = _ENTITY_LINK_RE.sub(_replace, narrative)
    if stripped:
        cleaned = re.sub(r"  +", " ", cleaned)
    return {"narrative": cleaned, "stripped": stripped}


# ── F9: out-of-corpus named-event attribution guard ──────────────────────────
# Reviewer Q7: asked about "ASCO 2025" (a congress the corpus has no data on), the
# model fabricated "...ASCO 2025 highlighted advancements... particularly
# cardiovascular risks..." — attributing generic literature to a named real-world
# event, with full confidence and no citations. The closed-world prompt forbids
# this but is advisory; the model ignores it under a named-event question. This is
# the deterministic enforcement: a named congress/event in the QUESTION whose token
# never appears in the retrieved EVIDENCE is out of corpus, so any attribution to it
# in the narrative is stripped/reframed (the surrounding real prose survives).

# Medical & scientific congress acronyms (UPPERCASE, matched case-sensitively so a
# lowercase common word — "chest", "endo", "ada" — can never trip the guard).
_CONGRESS_ACRONYMS = (
    "ASCO", "ESMO", "AACR", "ASH", "SABCS", "WCLC", "AHA", "ACC", "ESC", "HFSA",
    "EASD", "ADA", "ACR", "EULAR", "AAN", "ATS", "ERS", "DDW", "UEG", "EASL",
    "AASLD", "ASN", "ENDO", "ECTRIMS", "AAIC", "CTAD", "ISTH", "ASBMR",
)
# Plausible conference year (1900-2099), bounded so a dose / id ("ASCO 90210",
# "ESC 1234 study") is never misread as a year.
_CONF_YEAR = r"(?:19|20)\d{2}"
# A meeting/event noun that, DIRECTLY ADJACENT to the acronym, disambiguates it from
# a clinical homonym (ADA = anti-drug antibody, ESC = embryonic stem cell, ACC =
# acetyl-CoA-carboxylase). Adjacency is the safeguard: a meeting word elsewhere in
# the sentence must NOT promote a bare homonym (the prior whole-question scan made
# "Were ADA results presented?" fire — the exact over-firing class a past
# _TRIAL_COUNT_RE bug already cost a PR).
_MEETING_NOUN = (
    r"(?:annual\s+)?(?:congress|conference|meeting|symposi\w+|sessions?|summit|"
    r"abstracts?|plenar\w+|presentations?|readouts?)"
)
# Acronym + a REQUIRED-ADJACENT disambiguator. Groups: g1=acronym, g2=year (opt),
# g3=trailing meeting noun (opt); a fire needs g2 OR g3 (enforced in the detector).
# The acronym stays case-sensitive (no global re.I) so a lowercase homonym is never
# matched; the year/meeting parts are inherently/scoped case-insensitive.
_CONGRESS_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _CONGRESS_ACRONYMS) + r")\b"
    r"(?:[\s,'’-]+(" + _CONF_YEAR + r")\b)?"
    r"(?:\s+(?i:(" + _MEETING_NOUN + r")))?"
)
# Attribution verbs the model uses to source claims to an event subject.
_EVENT_ATTRIB_VERB = (
    r"highlight\w*|show(?:ed|cas\w*|s|n)?|report\w*|reveal\w*|present\w*|"
    r"feature\w*|demonstrat\w*|unveil\w*|spotlight\w*|focus\w*|underscor\w*|"
    r"emphasi[sz]\w*|cover\w*|includ\w*"
)
# Intervening event-noun a subject attribution may carry ("ASCO 2025's DATA showed",
# "the ASCO 2025 ABSTRACTS demonstrated") between the event and the verb.
_EVENT_SUBJECT_NOUN = r"data|abstracts?|results?|readouts?|sessions?|presentations?|trials?|studies|findings?"


def detect_out_of_corpus_events(question: str, evidence_text: str = "") -> list[dict]:
    """Named congress/event anchors in ``question`` that the retrieved evidence
    never mentions — i.e. out of corpus. Returns ``[{"acronym","year","display"}]``.

    Conservative on three axes (over-firing strips real prose):
      * a match counts as a NAMED EVENT only when a year OR a meeting noun is
        DIRECTLY ADJACENT to the acronym — a bare clinical homonym (ADA antibody,
        ESC stem cell) with a meeting word elsewhere in the sentence does NOT fire;
      * acronyms are matched case-sensitively (uppercase), so a lowercase homonym
        ("chest", "endo", "ada") is never matched;
      * an anchor is OUT OF CORPUS when its congress is absent from the evidence —
        YEAR-SPECIFIC when the question names a year (ASCO 2024 evidence does not
        support an ASCO 2025 question; pharma congress data is year-bound), and
        acronym-level when no year is requested.
    """
    q = question or ""
    if not q:
        return []
    blob = evidence_text or ""
    events: list[dict] = []
    seen: set[str] = set()
    for m in _CONGRESS_RE.finditer(q):
        acronym, year, meeting = m.group(1), m.group(2), m.group(3)
        if not year and not meeting:
            continue  # bare homonym, no adjacent year/meeting noun — not an event
        # Support is YEAR-SPECIFIC when the question names a year: pharma congress
        # data is year-bound, so ASCO 2024 evidence must NOT support an ASCO 2025
        # question (reviewer finding). The acronym and the requested year must be
        # CO-LOCATED in the evidence — a short window, either order, within a line
        # — so an incidental "2025" elsewhere (an approval/enrollment date, a trial
        # id) cannot stand in for actual ASCO-2025 coverage (independent whole-blob
        # searches were defeated by any stray year token; reviewer NIT). With no
        # requested year, acronym-level support is sufficient.
        if year:
            acr = re.escape(acronym)
            supported = bool(
                re.search(rf"\b{acr}\b.{{0,8}}?\b{year}\b", blob)
                or re.search(rf"\b{year}\b.{{0,8}}?\b{acr}\b", blob)
            )
        else:
            supported = bool(re.search(rf"\b{re.escape(acronym)}\b", blob))
        if supported:
            continue  # the requested congress (+ year, if named) is in the evidence
        display = f"{acronym} {year}" if year else acronym
        if display in seen:
            continue
        seen.add(display)
        events.append({"acronym": acronym, "year": year, "display": display})
    return events


def strip_unsupported_event_attributions(narrative: str, events: list[dict]) -> dict:
    """Neutralize attributions to out-of-corpus named events in ``narrative``.

    Two deterministic rewrites, keeping the surrounding (real) prose:
      * prepositional — "... at/from/during/per/according to [the] <event>
        [meeting] ..." → drop the attribution clause (it was not sourced there).
      * subject — "[The] <event>['s] [data/abstracts] highlighted/showed/reported
        ..." → "the available evidence <verb> ..." (the claim survives, the false
        source does not). Consumes a leading article so no "The the" is left.
    Idempotent. Returns ``{"narrative": str, "stripped": int}``.
    """
    if not narrative or not events:
        return {"narrative": narrative or "", "stripped": 0}
    acr_alt = "|".join(re.escape(e["acronym"]) for e in events)
    # acronym + optional bounded year + optional trailing meeting noun. Acronym
    # case-sensitive; year/meeting parts scoped case-insensitive.
    anchor = (
        rf"(?:{acr_alt})\b(?:[\s,'’-]+{_CONF_YEAR}\b)?"
        rf"(?:\s+(?i:{_MEETING_NOUN}))?"
    )
    # 1) prepositional attribution → removed (incl. "according to" / "as reported at")
    prep = re.compile(
        rf"\s*(?i:\b(?:at|during|from|per|according\s+to|"
        rf"as\s+(?:reported|presented|shown)(?:\s+(?:at|by|in|during))?)\b)"
        rf"\s+(?:(?i:the)\s+)?{anchor}"
    )
    out, n1 = prep.subn("", narrative)
    # 2) "[The] <event>['s] [noun] <verb>" subject → "the available evidence <verb>"
    subj = re.compile(
        rf"(?i:\bthe\s+)?\b{anchor}(?:['’]s)?"
        rf"(?:\s+(?i:{_EVENT_SUBJECT_NOUN}))?\s+((?i:{_EVENT_ATTRIB_VERB})\b)"
    )
    out, n2 = subj.subn(r"the available evidence \1", out)
    stripped = n1 + n2
    if stripped:
        out = re.sub(r"[ \t]{2,}", " ", out)             # collapse double spaces
        out = re.sub(r"\s+([.,;:])", r"\1", out)         # space before punctuation
        out = re.sub(r"(^|[.!?]\s+)\s*,\s*", r"\1", out) # orphan comma at sentence start
        out = re.sub(r"^\s+", "", out)                   # leading whitespace
        # capitalize the sentence-initial reframed subject
        out = re.sub(
            r"(^|(?<=[.!?]\s))the available evidence", "The available evidence", out
        )
        # recapitalize a sentence start lowercased by a removed prep clause; guarded
        # by a following lowercase letter so acronyms/terms (mRNA, siRNA) survive.
        out = re.sub(
            r"(^|[.!?]\s+)([a-z])(?=[a-z])",
            lambda mm: mm.group(1) + mm.group(2).upper(), out,
        )
    return {"narrative": out, "stripped": stripped}


def validate_citations(narrative: str, evidence_count: int) -> dict:
    """Validate citation markers in narrative.

    Three kinds of citations are counted:
      [N]          — evidence index (must be 1 <= N <= evidence_count)
      [Name](/entity/{type}/{id}) — click-through entity link (SPEC_016 §1B)

    Strips invalid [N] markers. Does NOT strip entity links — they trace to
    the DB and can be separately validated by the ContextGuard.

    Returns: {
      "narrative": cleaned_text,
      "valid": int,             # valid [N] count
      "stripped": int,          # [N] markers that were removed
      "entity_links": int,      # click-through [Name](/entity/...) count
    }
    """
    if not narrative:
        return {"narrative": "", "valid": 0, "stripped": 0, "entity_links": 0}

    valid = 0
    stripped = 0

    def _replace(match):
        nonlocal valid, stripped
        n = int(match.group(1))
        if 1 <= n <= evidence_count:
            valid += 1
            return match.group(0)  # keep
        stripped += 1
        logger.debug("Stripped invalid citation [%d] (evidence_count=%d)", n, evidence_count)
        return ""  # remove

    cleaned = _CITATION_RE.sub(_replace, narrative)
    # Clean up double spaces from removed citations
    cleaned = re.sub(r"  +", " ", cleaned)

    # Count click-through entity links (don't mutate — they stay in the text
    # and render as clickable in the UI).
    entity_links = len(_ENTITY_LINK_RE.findall(cleaned))

    return {
        "narrative": cleaned,
        "valid": valid,
        "stripped": stripped,
        "entity_links": entity_links,
    }


_BOLD_NUMBER_RE = re.compile(r"\*\*(\d+(?:\.\d+)?%?)\*\*")
_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")

# A metrics row carries a figure as a display string ("1530.4", "47", "23%",
# "2.5x", "1,530"); such a value is numeric-dominant. We mine numbers from a
# string ONLY when it is value-like — NOT from a free-text label, where a digit
# inside a date or id ("Report dated 2023-04-23, id 999") would launder an
# invented narrative number into a "grounded" one. Letters (month-name dates,
# ids, labels) and dashed/ISO dates are excluded (the dash is not in the class);
# a single trailing %/x/× unit is allowed.
_VALUE_LIKE_RE = re.compile(r"[\d.,\s]*\d[\d.,\s]*[%xX×]?")
# Boundary-free number scan for already-gated value-like strings — captures a
# figure carrying a trailing unit ("2.5x" -> 2.5, "82.5%" -> 82.5), which the
# word-boundary ``_NUMBER_RE`` misses ("2.5x" has no \b before the word-char x).
_VALUE_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# Unbolded statistical figures the model is prone to invent: a percentage
# ("23% weight loss") or a multiplier ("2.5x pipeline score", "3× more").
# Deliberately narrow — it must NOT match identifiers like "GLP-1",
# "Type 2", "Phase 3", "8.1" inside a token — only numbers that carry a
# statistical unit (% or x/× multiplier). The leading lookbehind rejects a
# hyphen/letter prefix so "GLP-1" never matches.
_UNBOLDED_STAT_RE = re.compile(
    r"(?<![\w\-.])(\d+(?:\.\d+)?)\s?([%xX×])(?![\w])"
)

# Internal, NON-LEAKING sentinel used only to dedup the two verification
# passes — a figure de-emphasised in pass 1 (bold) must not be re-counted in
# pass 2 (unbolded). It is stripped before the narrative is returned and must
# NEVER reach a user. (F6 / TICKET-5: the prior visible " [unverified]" string
# leaked into answers and — worse — made grounded, authoritative figures look
# untrustworthy. De-emphasis is now bold-removal only; the audit signal lives in
# the returned counts + the server-side log, not in user-facing prose.)
_DEDUP_SENTINEL = "\x00\x00"


def _extract_source_numbers(metrics: dict | None, evidence_snippets: list[str] | None) -> set[float]:
    """Extract all numeric values from metrics context and evidence for verification."""
    numbers: set[float] = set()
    if metrics:
        _collect_numbers_from_dict(metrics, numbers)
    if evidence_snippets:
        for snippet in evidence_snippets[:10]:
            for m in _NUMBER_RE.finditer(str(snippet)):
                try:
                    numbers.add(float(m.group(1)))
                except ValueError:
                    pass
    return numbers


def _collect_numbers_from_dict(d: dict | list, out: set[float], depth: int = 0) -> None:
    """Recursively collect numeric values from nested dict/list.

    Numbers embedded in *value-like string* values are collected too — metrics
    rows routinely carry provenance-stamped figures as display strings (e.g.
    ``{"metric": "Pipeline Score", "value": "1530.4"}``, the shape
    ``services/chat_handlers/handlers.py`` builds). Without this a computed,
    authoritative metric would be flagged as unverified in the narrative (F6 /
    TICKET-5). Only numeric-dominant strings (``_VALUE_LIKE_RE``) are mined, so a
    free-text label's incidental date/id digits do not leak into the grounded
    set — every figure in a metrics *value* is grounded by definition.
    """
    if depth > 5:
        return
    values = d.values() if isinstance(d, dict) else d if isinstance(d, list) else ()
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.add(float(v))
        elif isinstance(v, str):
            s = v.strip()
            if not _VALUE_LIKE_RE.fullmatch(s):
                continue  # free-text label — don't mine its date/id digits
            for tok in _VALUE_NUM_RE.findall(s):
                try:
                    out.add(float(tok))
                except ValueError:
                    pass
        elif isinstance(v, (dict, list)):
            _collect_numbers_from_dict(v, out, depth + 1)


def _is_grounded_number(num: float, source_numbers: set[float | int], tolerance: float) -> bool:
    """True if `num` is within `tolerance` of any source number (or its
    percentage form, e.g. narrative 82 ≈ source 0.82)."""
    for src in source_numbers:
        src_f = float(src)
        if abs(num - src_f) <= tolerance:
            return True
        # Percentage form: narrative "82%" matches source 0.82
        if 0 < src_f < 1 and abs(num - src_f * 100) <= tolerance:
            return True
        # Inverse percentage form: narrative "0.82" matches source 82
        if 0 < num < 1 and abs(num * 100 - src_f) <= tolerance:
            return True
    return False


def verify_narrative_numbers(
    narrative: str,
    source_numbers: set[float | int],
    tolerance: float = 1.0,
) -> dict:
    """Verify the quantitative claims in a narrative against source data.

    Every number in a synthesized answer must trace to a provided
    DB/context value, or be de-emphasized — no invented stats. Two shapes
    are checked:

      1. **Bold** numbers (``**N**``, ``**N.N**``, ``**N%**``) — the model's
         emphasised claims.
      2. Unbolded *statistical* figures that carry a unit: percentages
         (``23% weight loss``) and multipliers (``2.5x pipeline score``).
         These are the invented-stat shapes; bare identifiers like
         ``GLP-1`` / ``Type 2`` / ``Phase 3`` are deliberately NOT matched.

    Numbers within `tolerance` of any source number are verified and left
    untouched. Unverified figures are DE-EMPHASISED: a bold figure has its
    bold (the trust signal) stripped; an already-unbolded figure is left in
    place. **No inline marker is written into the prose** — the prior visible
    ``[unverified]`` string leaked to readers and made grounded, authoritative
    numbers look untrustworthy (F6 / TICKET-5). The audit signal is preserved
    structurally instead: ``flagged`` / ``mismatches`` in the return value (and
    the caller's server-side log). Conservative by design — a legitimately
    cited number that appears in the context survives intact.

    Returns: {"narrative": str, "verified": int, "flagged": int,
              "stripped": int, "mismatches": [...]}
      - ``flagged``  — figures not grounded in the source (bold or unbolded).
      - ``stripped`` — bold trust-signals removed (a subset of ``flagged``).
    """
    if not narrative:
        return {"narrative": "", "verified": 0, "flagged": 0, "stripped": 0, "mismatches": []}

    verified = 0
    flagged = 0
    stripped = 0
    mismatches: list[float] = []

    # ── 1. Bold numbers ──────────────────────────────────────────────
    for raw in _BOLD_NUMBER_RE.findall(narrative):
        clean = raw.rstrip("%")
        try:
            num = float(clean)
        except ValueError:
            continue
        if _is_grounded_number(num, source_numbers, tolerance):
            verified += 1
        else:
            flagged += 1
            stripped += 1
            mismatches.append(num)
            # De-emphasise: remove the bold trust signal. No user-visible
            # marker — an internal sentinel dedups pass 2 and is stripped
            # before return (the literal " [unverified]" must not leak).
            narrative = narrative.replace(
                f"**{raw}**", f"{raw}{_DEDUP_SENTINEL}", 1
            )

    # ── 2. Unbolded statistical figures (%, x-multiplier) ────────────
    # Re-scan the (possibly already-modified) narrative. Skip figures we
    # handled in pass 1 (they carry the internal sentinel) and any already
    # inside a bold span we left intact (verified bold numbers).
    def _replace_unbolded(m: re.Match) -> str:
        nonlocal verified, flagged
        whole = m.group(0)
        # Don't re-count a figure already handled in pass 1.
        tail = narrative[m.end():m.end() + len(_DEDUP_SENTINEL)]
        if tail == _DEDUP_SENTINEL:
            return whole
        try:
            num = float(m.group(1))
        except ValueError:
            return whole
        # For multipliers, verify the bare value (2.5x ↔ source 2.5).
        # For percentages, _is_grounded_number already handles 82 ↔ 0.82.
        if _is_grounded_number(num, source_numbers, tolerance):
            verified += 1
            return whole
        # Record it (server log / mismatches) but leave the text intact —
        # an unbolded figure has no bold to strip, and we must not leak a
        # marker. The honesty backstop here is structural, not in the prose.
        flagged += 1
        mismatches.append(num)
        return whole

    narrative = _UNBOLDED_STAT_RE.sub(_replace_unbolded, narrative)

    # Strip the internal dedup sentinel — it must never reach the user.
    narrative = narrative.replace(_DEDUP_SENTINEL, "")

    return {
        "narrative": narrative,
        "verified": verified,
        "flagged": flagged,
        "stripped": stripped,
        "mismatches": mismatches,
    }


_BASE_RULES = """- Use **bold** for key entities, numbers, and findings.
- STRICT DATA GROUNDING: ONLY use numbers, percentages, and facts that appear in the PROVIDED CONTEXT below. Do NOT supplement with knowledge from your training data. No clinical efficacy numbers, no MACE reductions, no survival rates unless explicitly in the context.
- If the data is thin, say so honestly ("limited data available for X") rather than padding with external knowledge.
- CITATIONS: When you reference a specific fact, include the evidence number in square brackets inline, e.g. [1], [2]. Cite EVIDENCE items by their number. If there is a METRICS section, reference it as [metrics]. Only cite numbers that actually exist in the provided context. If there is NO EVIDENCE section and no METRICS section, do NOT use any citation markers.
- AIM for at least 2 citations per paragraph when evidence is available. Every factual claim should be traceable to a source."""

SYSTEM_PROMPTS: dict[str, str] = {
    "compare": f"""You are a senior pharmaceutical intelligence analyst. You are comparing entities head-to-head.

Rules:
- Lead with the most decision-relevant DIFFERENCE the data actually supports —
  mechanism of action, approved indication, or head-to-head evidence — NOT a winner
  declared from trial counts.
- State differentials precisely AND label what they mean: "X has N more registered
  trials in our data" describes the breadth/maturity of a development programme, it
  does NOT mean X is the stronger or better drug.
- Do NOT declare one entity "stronger"/"better"/"winning" overall unless head-to-head
  efficacy or outcome evidence is present in the context. If it is absent, say the
  comparison is limited to the dimensions the data covers, and name what is missing.
- Mechanism matters most: if two drugs differ in mechanism (e.g. a GLP-1 agonist vs a
  dual GIP/GLP-1 agonist), that difference is the headline — never flatten it.
- Compute and state differentials, don't just list numbers side-by-side. A comparison
  table is displayed alongside — don't restate every number.
- CRITICAL: ONLY use numbers and facts from the PROVIDED CONTEXT below. Do NOT inject
  clinical trial results, efficacy percentages, MACE reductions, or any other
  statistics from your training data. If the data doesn't cover a dimension, say so
  rather than filling in from memory.
- If COMPUTED DIFFERENTIALS are provided, use those exact numbers.
- End with a verdict ONLY for the dimensions the data supports; otherwise end by
  stating what further evidence (e.g. head-to-head efficacy) a real decision needs.
- 2-3 paragraphs maximum.
{_BASE_RULES}""",

    "landscape": f"""You are a senior pharmaceutical intelligence analyst. You are analyzing a competitive market landscape.

The data is segmented by THERAPEUTIC AREA (disease indication), NOT by company. Each row represents a therapeutic area where the queried mechanism/drug class is used.

Rules:
- Lead with the concentration insight — which therapeutic areas dominate activity for this mechanism.
- Name the top segments by their therapeutic area and distinguishing metric (drug count, trial volume, pipeline score).
- Do NOT say "dominated by companies" — the segments are therapeutic areas, not companies.
- If therapeutic areas overlap (e.g. "Diabetes Mellitus" and "Diabetes Mellitus, Type 2"), note that broader categories include subcategories and avoid double-counting.
- Note any gaps or underserved therapeutic areas worth investigating.
- 2-3 sentences maximum. A data table is displayed alongside — reference it naturally.
{_BASE_RULES}""",

    "leaders": f"""You are a senior pharmaceutical intelligence analyst. The user asked WHICH COMPANIES lead/dominate a therapeutic area or drug class.

The EVIDENCE includes a ranked list of companies (MARKET LEADERS) by number of drugs in this area, plus competitive context by mechanism.

Rules:
- LEAD by NAMING the top companies explicitly (e.g. "Eli Lilly and Novo Nordisk lead..."), with their drug/trial counts from the evidence.
- Only name companies that appear in the provided EVIDENCE/MARKET LEADERS data. NEVER name a company that is not in the data, and never name device makers or research institutes as market leaders.
- After the companies, you MAY add one sentence on the mechanism-level competition (GLP-1, SGLT2, etc.) for context.
- Every company drug/trial count MUST carry a citation [N] or [metrics].
- 2-3 sentences. A table is displayed alongside.
{_BASE_RULES}""",

    "pipeline": f"""You are a senior pharmaceutical intelligence analyst. You are reporting on drug pipeline metrics.

Rules:
- Lead with the headline finding: who leads and with what score.
- Note the phase distribution (early vs. late stage strength).
- Compare to benchmarks when possible (typical Phase 2→3 success ~30%, Phase 3→approval ~60%).
- 2-3 sentences maximum. A pipeline table is displayed alongside.
{_BASE_RULES}""",

    "portfolio": f"""You are a senior pharmaceutical intelligence analyst. You are briefing on a company portfolio.

Rules:
- Lead with the company's position: how many drugs, in what therapeutic areas.
- Note pipeline maturity (early vs. late stage balance).
- Highlight any standout drugs or competitive gaps.
- 2-3 paragraphs maximum. A summary table is displayed alongside.
{_BASE_RULES}""",

    "dossier": f"""You are a senior pharmaceutical intelligence analyst briefing an executive.

Rules:
- Lead with what the entity is and its significance.
- Key metrics in bold: pipeline score, trial count, phase distribution.
- Note any recent developments or notable trial activity.
- EVERY numeric claim MUST have a citation [N] or [metrics] tag immediately after it.
- If data is missing or limited, say "data is limited" — NEVER invent numbers.
- Name connected entities (company, mechanism, therapeutic area) when available.
- Include competitive context if mechanism or therapeutic area peers exist in the data.
- 2-4 paragraphs maximum.
{_BASE_RULES}""",

    "tabular": f"""You are a senior pharmaceutical intelligence analyst. The user asked for structured/tabular output.

Rules:
- Write 1-2 sentences ONLY as a brief summary header.
- Do NOT restate numbers from the table — a full data table is displayed below.
- Simply describe what the table shows and call out 1-2 notable patterns.
{_BASE_RULES}""",

    "default": f"""You are a senior pharmaceutical intelligence analyst at a top-tier strategy consulting firm.

Rules:
- Write 2-4 paragraphs maximum. Be concise but insightful.
- Lead with the most important finding or insight.
- Use specific numbers from the data provided.
- Highlight competitive dynamics, risks, and opportunities when relevant.
- You may use bullet points or short lists when they improve clarity.
{_BASE_RULES}""",
}

# Backward-compatible alias
SYSTEM_PROMPT = SYSTEM_PROMPTS["default"]


_CITATION_PROTOCOL = """
CITATION PROTOCOL (SPEC_016):
- Every factual claim MUST cite evidence. Use [N] markers where N is a
  1-based index into the evidence list in the context.
- When you mention an entity (drug, company, trial, mechanism, investigator)
  write it as a clickable markdown link:
      [Entity Name](/entity/{type}/{id})
  The {id} is a PLACEHOLDER — substitute the real id from the context. If the
  context gives no id for an entity, write the name as plain text with NO link.
  NEVER emit a literal placeholder id (e.g. EXAMPLE_ID_DO_NOT_COPY); an invented
  id renders as a broken citation and will be stripped.
- Never invent numbers. Every percentage / count / score must come from
  the data above.
"""


# The closed-world / calibration guard. Appended to EVERY synthesis prompt so the
# reasoning layer stops turning database artefacts into confident verdicts — the
# semaglutide-vs-tirzepatide failure class. Targets eval gates G1 (provenance),
# G2 (closed-world honesty) and G3 (no count fallacy). See benchmark/eval_pharma_v1.yaml.
_CLOSED_WORLD_PROTOCOL = """
CLOSED-WORLD & CALIBRATION PROTOCOL (binding — it overrides any instinct to sound
confident or complete):
- The context below is only what THIS PLATFORM has ingested — not everything that
  is true in the world. Absence in the data is NOT evidence of absence in reality.
  If a required dimension is empty, thin, or not covered, state that as a known
  limitation. NEVER convert a gap in retrieval into a negative conclusion — phrases
  like "no competitors", "limited regulatory data suggests uncertainty", or "not
  approved" are FORBIDDEN when the real reason is that the data was not retrieved.
  Surface such gaps as explicit unknowns instead.
- Counts are not quality. Trial counts, record counts and pipeline scores measure
  time-on-market and breadth of ingest — NOT efficacy, safety, or commercial
  strength. NEVER rank entities or call one "stronger"/"better"/"more advanced"
  overall on the basis of counts alone. A larger trial count means a broader or
  older development programme; say exactly that and no more.
- Scope every verdict to the axis the data supports. "More registered trials in our
  data" is a claim the data licenses; "the stronger asset" is not, unless
  head-to-head efficacy or outcome evidence is actually present. When efficacy,
  safety, approval or pricing data is absent, do NOT render an overall verdict —
  present what is known and name what is missing for a real decision.
- Attribute EVERY factual claim to its named source, INLINE in the prose. Each
  evidence snippet carries a "[source: <connector>]" marker — e.g.
  [source: ClinicalTrials.gov], [source: openFDA FAERS], [source: MeSH / curated
  mechanism], [source: drugs@FDA registry], [source: FDA drug products / labels].
  For each fact you state you MUST name that source IN THE SENTENCE ITSELF, in
  addition to the [N] citation. Use the EXACT source name from the marker. Examples:
    • "Per ClinicalTrials.gov, semaglutide has 47 registered trials [3]."
    • "Its mechanism is a GLP-1 receptor agonist (per MeSH / curated mechanism) [2]."
    • "The marketing applicant is Novo Nordisk (drugs@FDA registry) [1]."
  A factual sentence with NO named source is INCOMPLETE — do not state a fact you
  cannot attribute, and never invent a source that is not in a marker. Naming the
  source lets the reader weigh its reliability and freshness.
"""


def _assemble_system_prompt(base: str) -> str:
    """The EXACT text shipped to the model for a base prompt: base + citation
    protocol + closed-world guard. Single source of truth so the prompt-registry
    row (register_synthesis_prompts) stays 1:1 with what actually ships."""
    return base + "\n\n" + _CITATION_PROTOCOL + "\n" + _CLOSED_WORLD_PROTOCOL


def _get_system_prompt(intent: str, format_hint: str | None = None) -> str:
    """Select the best system prompt based on intent and format hint.

    SPEC_016 §1B: appends the citation protocol (click-through entity links) and
    the closed-world/calibration guard to every prompt regardless of intent so the
    response layer is consistent and honest about ingest limits.
    """
    if format_hint == "table":
        base = SYSTEM_PROMPTS["tabular"]
    else:
        base = SYSTEM_PROMPTS.get(intent, SYSTEM_PROMPTS["default"])
    return _assemble_system_prompt(base)


# ── C1 depth: prompt-versioned synthesis ───────────────────────────
#
# Every synthesis system prompt is registered in `prompt_registry` so each
# llm_call_log row can carry a non-null prompt_id (the Learning Service
# attributes calibration to specific prompt versions). The registered
# `content` is the EXACT text shipped to the model — `_get_system_prompt`
# output (base prompt + citation protocol) — so the registry row is a
# faithful audit of what was sent.

# Prompt-registry name prefix; one prompt per intent key in SYSTEM_PROMPTS.
SYNTHESIS_PROMPT_PREFIX = "synthesis."

# Process-local cache: (intent) -> prompt_id. Avoids a registry round-trip on
# every synthesis call. Populated lazily by _resolve_prompt_id / registration.
_SYNTHESIS_PROMPT_ID_CACHE: dict[str, str] = {}


def _synthesis_prompt_name(intent: str, format_hint: str | None = None) -> str:
    """Registry name for the system prompt actually used for this call.
    Mirrors _get_system_prompt's selection (table → tabular, else intent or
    default), so the logged prompt_id matches the shipped text 1:1."""
    if format_hint == "table":
        key = "tabular"
    else:
        key = intent if intent in SYSTEM_PROMPTS else "default"
    return f"{SYNTHESIS_PROMPT_PREFIX}{key}"


def register_synthesis_prompts(db) -> dict[str, str]:
    """Register every synthesis system prompt in `prompt_registry` (idempotent).

    Reuses `PromptRegistry.register` — same (name, content) returns the
    existing row, different content bumps the version. Returns a mapping of
    registry name -> prompt_id and primes the process-local cache.

    Safe to call repeatedly (e.g. on startup); no-op when content unchanged.
    """
    from services.llm_gateway import PromptRegistry

    out: dict[str, str] = {}
    for key in SYNTHESIS_PROMPTS_KEYS:
        name = f"{SYNTHESIS_PROMPT_PREFIX}{key}"
        # The shipped text for this key = base prompt + citation protocol +
        # closed-world guard. Use the same assembler _get_system_prompt uses so
        # the registry row is a faithful 1:1 audit of what was sent.
        content = _assemble_system_prompt(SYSTEM_PROMPTS[key])
        try:
            prompt = PromptRegistry.register(
                db,
                name=name,
                content=content,
                purpose=f"LLMSynthesizer system prompt for intent={key!r}",
            )
            out[name] = str(prompt.prompt_id)
            _SYNTHESIS_PROMPT_ID_CACHE[key] = str(prompt.prompt_id)
        except Exception:
            logger.warning("register_synthesis_prompts failed for %s", name, exc_info=True)
    return out


SYNTHESIS_PROMPTS_KEYS = tuple(SYSTEM_PROMPTS.keys())


def _resolve_synthesis_prompt_id(db, intent: str, format_hint: str | None = None) -> Optional[str]:
    """Resolve the prompt_id for the system prompt used by this synthesis call.

    Order: process cache → registry lookup by latest version → lazy register.
    Returns None only when no db handle or every path fails (logging then
    falls back to a null prompt_id, exactly as before C1).
    """
    if db is None:
        return None
    key = "tabular" if format_hint == "table" else (intent if intent in SYSTEM_PROMPTS else "default")
    cached = _SYNTHESIS_PROMPT_ID_CACHE.get(key)
    if cached:
        return cached
    name = f"{SYNTHESIS_PROMPT_PREFIX}{key}"
    try:
        from services.llm_gateway import PromptRegistry
        existing = PromptRegistry.get_latest(db, name)
        if existing:
            _SYNTHESIS_PROMPT_ID_CACHE[key] = str(existing.prompt_id)
            return str(existing.prompt_id)
        # Not registered yet — register on demand so the very first call logs
        # a non-null prompt_id rather than waiting for a startup hook.
        register_synthesis_prompts(db)
        return _SYNTHESIS_PROMPT_ID_CACHE.get(key)
    except Exception:
        logger.debug("prompt_id resolution failed for %s", name, exc_info=True)
        return None

RESEARCH_SYSTEM_PROMPT = """You are preparing a decision-support research brief for a pharmaceutical leadership team.

Rules:
- Use clear section headers.
- Be factual and conservative in claims.
- Distinguish internal graph evidence from external web context.
- Do not invent data or citations.
- Keep recommendations actionable and specific to evidence.
- Maximum length: 700 words.
"""


def _compress_evidence(
    evidence_snippets: Optional[list[str]],
    question: str = "",
) -> tuple[Optional[list[str]], Optional[str]]:
    """Try to compress evidence snippets via ctxpack entity resolution.

    Returns (snippets, compressed_block):
    - If compression succeeded: (None, compressed_text) — use compressed_block as extra_context
    - If passthrough/unavailable: (original_snippets, None) — use snippets normally
    """
    if not evidence_snippets:
        return evidence_snippets, None

    try:
        from services.ctx_evidence import pack_evidence
        items = [{"content": s} for s in evidence_snippets]
        compressed_text, metrics = pack_evidence(items, question=question)

        if metrics.get("mode") == "ctx":
            logger.info(
                "Evidence compressed: %d → %d tokens (%.1fx, %d merged)",
                metrics.get("raw_tokens", 0),
                metrics.get("compressed_tokens", 0),
                metrics.get("ratio", 1),
                metrics.get("merged", 0),
            )
            return None, f"EVIDENCE (compressed):\n{compressed_text}"
        else:
            return evidence_snippets, None
    except Exception as e:
        logger.debug("Evidence compression unavailable: %s", e)
        return evidence_snippets, None


def _build_context_block(
    question: str,
    intent: str,
    entity_info: Optional[dict] = None,
    metrics: Optional[dict] = None,
    graph_summary: Optional[dict] = None,
    evidence_snippets: Optional[list[str]] = None,
    extra_context: Optional[str] = None,
    ctx_mode: str = "ctx",
) -> str:
    """Build a structured context block for the LLM.

    Pipeline:
    1. Compress evidence snippets via ctxpack entity resolution (if above threshold)
    2. Assemble full context via CTXContextBuilder (with threshold gate)
    3. Append few-shot exemplars for citation density
    4. Fall back to legacy flat format on failure

    ctx_mode: "ctx" (default) | "legacy"
    """
    # Step 1: Try to compress evidence before context assembly
    snippets_for_ctx, compressed_evidence = _compress_evidence(
        evidence_snippets, question=question,
    )

    # If evidence was compressed, append it to extra_context
    if compressed_evidence:
        if extra_context:
            extra_context = f"{extra_context}\n\n{compressed_evidence}"
        else:
            extra_context = compressed_evidence

    context = None
    try:
        from services.ctx_context import CTXContextBuilder
        builder = CTXContextBuilder(mode=ctx_mode)
        ctx_result = builder.build(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=snippets_for_ctx,
            extra_context=extra_context,
        )

        # Fire-and-forget telemetry
        try:
            from services.telemetry import log_ctx_event
            from api.deps import get_db
            log_ctx_event(
                db=get_db(),
                question=question,
                intent=intent,
                ctx_tokens=ctx_result.tokens,
                compression_ratio=ctx_result.compression_ratio,
                build_time_ms=ctx_result.build_time_ms,
                mode=ctx_result.mode,
            )
        except Exception:
            pass  # telemetry must never break the main flow

        context = ctx_result.text
    except Exception as e:
        logger.warning("CTX context builder failed, falling back to legacy: %s", e)
        # Fallback to legacy inline
        parts = [f"USER QUESTION: {question}", f"INTENT: {intent}"]
        if entity_info:
            parts.append(f"ENTITY: {json.dumps(entity_info, default=str)}")
        if metrics:
            parts.append(f"METRICS: {json.dumps(metrics, default=str)}")
        if graph_summary:
            parts.append(f"GRAPH CONTEXT: {json.dumps(graph_summary, default=str)}")
        if snippets_for_ctx:
            parts.append("EVIDENCE:")
            for i, snippet in enumerate(snippets_for_ctx[:10], 1):
                parts.append(f"  [{i}] {snippet}")
        if extra_context:
            parts.append(f"ADDITIONAL CONTEXT: {extra_context}")
        context = "\n\n".join(parts)

    # Step 3: Append few-shot exemplars for citation density
    try:
        from services.few_shot_library import FewShotLibrary
        _few_shot_lib = FewShotLibrary()
        exemplars = _few_shot_lib.get_exemplars(intent, max_examples=2)
        if exemplars:
            context += "\n\n" + _few_shot_lib.format_context(exemplars)
    except Exception as e:
        logger.debug("Few-shot library unavailable: %s", e)

    # Step 4 (SPEC_016 §1C): L3 universe summary at the HEAD of context so the
    # LLM knows the world is finite before reading evidence. Cheap (cached 5min).
    try:
        from services.ctx_corpus import get_l3_summary
        from api.deps import get_db
        l3 = get_l3_summary(get_db())
        if l3:
            context = f"{l3}\n\n{context}"
    except Exception as exc:
        logger.debug("L3 summary unavailable: %s", exc)

    # Step 5 (SPEC_016 §1A): Sandwich grounding — tail reminder AFTER evidence.
    # Mirrors intelligent_enterprise/app/api/chat/route.ts:148-153. LLMs are
    # known to forget head instructions by the time they finish reading a
    # long context; repeating the constraint at the tail catches mid-generation
    # drift.
    context += (
        "\n\n---\n"
        "BEFORE YOU RESPOND — GROUNDING CHECK:\n"
        "1. Every factual claim must appear in the context above. "
        "If you cannot find support for a statement, say so explicitly "
        "rather than filling in from general knowledge.\n"
        "2. Every entity you name (drug, company, trial, mechanism) "
        "must appear in the data above. Use ONLY the names shown — do "
        "not invent brand/generic/trade names that aren't in the context.\n"
        "3. When you mention an entity, write it as a markdown link: "
        "[Entity Name](/entity/{type}/{id}), substituting the REAL {id} from "
        "the data. If no id is available, omit the link and use plain text — "
        "never emit a placeholder id (it will be stripped as a broken link).\n"
        "4. Do not invent numeric values, percentages, or industry benchmarks. "
        "Every number must trace to the data above or be omitted."
    )

    return context


class LLMSynthesizer:
    """Synthesizes structured pharma data into analyst-grade narratives."""

    def __init__(self, config, db=None):
        self.config = config
        self._client = None
        # C1 (learning loops): optional DB handle so every production synthesis
        # call lands in llm_call_log 1:1 — closes the gateway-bypass gap (~26
        # logged calls vs ~78 chat queries). When db is None we behave exactly
        # as before: no logging, no extra dependency.
        self._db = db

    @property
    def enabled(self) -> bool:
        return (
            self.config.llm.enabled
            and bool(self.config.llm.api_key)
        )

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.config.llm.api_key)
        return self._client

    def _log_call(
        self,
        *,
        caller: str,
        model,
        prompt_text: str,
        completion_text,
        latency_ms: int,
        succeeded: bool,
        error=None,
        prompt_id: Optional[str] = None,
    ) -> None:
        """C1: persist one llm_call_log row. Fire-and-forget — telemetry must
        never break synthesis. No-op when no db handle was injected (preserves
        DB-free unit tests).

        C1 depth: when `prompt_id` is provided (resolved from the prompt
        registry) the row carries it, so the Learning Service can attribute
        calibration to a specific prompt version. When it's None we fall back
        to the shared `log_llm_call` helper (prompt_id stays NULL — old
        behaviour)."""
        if self._db is None:
            return
        try:
            from services.llm_telemetry import (
                log_llm_call, _est_tokens, _estimate_cost_usd,
            )
            prompt_tokens = _est_tokens(prompt_text)
            completion_tokens = _est_tokens(completion_text or "")
            if prompt_id is None:
                log_llm_call(
                    self._db,
                    caller=caller,
                    model=model,
                    prompt_version=getattr(self.config.llm, "ctx_mode", "ctx"),
                    user_id=None,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    succeeded=succeeded,
                    error_message=(str(error)[:500] if error else None),
                )
                return
            # prompt-versioned insert (mirrors LLMGateway.invoke's row shape)
            cost = _estimate_cost_usd(model, prompt_tokens, completion_tokens)
            self._db.execute(
                """INSERT INTO llm_call_log
                       (caller, model, prompt_version, user_id, latency_ms,
                        prompt_tokens, completion_tokens, cost_estimate_usd,
                        succeeded, error_message, prompt_id)
                   VALUES (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::uuid)""",
                [
                    caller, model, getattr(self.config.llm, "ctx_mode", "ctx"),
                    None, latency_ms, prompt_tokens, completion_tokens, cost,
                    succeeded, (str(error)[:500] if error else None), prompt_id,
                ],
            )
        except Exception:
            logger.debug("llm _log_call failed", exc_info=True)

    def _post_validate(
        self,
        narrative: str,
        evidence_count: int = 0,
        source_numbers: set | None = None,
        question: str = "",
        evidence_text: str = "",
    ) -> str:
        """Post-synthesis validation: citation check + numeric verification.

        Applied after every LLM synthesis to catch hallucinated citations
        and numeric drift from source data.
        """
        # Citation validation
        cit_result = validate_citations(narrative, evidence_count)
        narrative = cit_result["narrative"]
        if cit_result["stripped"] > 0:
            logger.info("Stripped %d invalid citation(s) from narrative", cit_result["stripped"])

        # Strip fabricated entity links (the abc-123 placeholder the model copies
        # from the prompt example). No valid-id set here, so only the known
        # sentinels are stripped — a safe both-path floor; the unified handler does
        # the full evidence-id validation where it has the evidence on hand.
        link_result = strip_invalid_entity_links(narrative)
        narrative = link_result["narrative"]
        if link_result["stripped"] > 0:
            logger.info("Stripped %d placeholder entity link(s) from narrative", link_result["stripped"])

        # Numeric verification — de-emphasise unverified numbers (bold stripped;
        # no inline marker leaks to the reader). The server-side log is the audit
        # signal for ALL flagged figures, bold or not (F6 / TICKET-5).
        if source_numbers:
            num_result = verify_narrative_numbers(narrative, source_numbers)
            narrative = num_result["narrative"]
            if num_result["flagged"] > 0:
                logger.warning(
                    "Flagged %d unverified number(s) (%d bold de-emphasised, no marker leaked): %s",
                    num_result["flagged"], num_result["stripped"], num_result["mismatches"],
                )

        # F9: neutralize attributions to a named congress/event absent from the
        # evidence (the ASCO-2025 fabrication). A both-path floor — the unified
        # handler additionally surfaces the explicit no-data coverage limit where
        # it owns the response contract.
        if question:
            events = detect_out_of_corpus_events(question, evidence_text)
            if events:
                ev_result = strip_unsupported_event_attributions(narrative, events)
                narrative = ev_result["narrative"]
                if ev_result["stripped"] > 0:
                    logger.info(
                        "Neutralized %d out-of-corpus event attribution(s): %s",
                        ev_result["stripped"], ", ".join(e["display"] for e in events),
                    )

        return narrative

    def raw_chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 900,
        temperature: float = 0.2,
    ) -> Optional[str]:
        """Direct chat completion bypass for callers that build their own
        prompts (e.g. SPEC-021 war game reaction engine).

        Returns the assistant's text content or None if the LLM is
        unavailable / all model attempts fail. Tries the primary model
        then the fallback, same retry shape as synthesize().
        """
        if not self.enabled:
            return None

        primary_model = self.config.llm.model
        fallback_model = getattr(self.config.llm, "fallback_model", primary_model)
        models = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models.append(fallback_model)

        client = self._get_client()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        import time as _time
        _t0 = _time.perf_counter()
        _last_err = None
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    self._log_call(
                        caller="llm.raw_chat", model=model,
                        prompt_text=system + "\n" + user, completion_text=text,
                        latency_ms=int((_time.perf_counter() - _t0) * 1000),
                        succeeded=True,
                    )
                    return text
            except Exception as e:
                _last_err = e
                logger.warning("raw_chat model %s failed: %s", model, e)
                continue
        self._log_call(
            caller="llm.raw_chat", model=(models[-1] if models else None),
            prompt_text=system + "\n" + user, completion_text=None,
            latency_ms=int((_time.perf_counter() - _t0) * 1000),
            succeeded=False, error=_last_err,
        )
        return None

    def synthesize(
        self,
        question: str,
        intent: str,
        entity_info: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        fallback_narrative: str = "",
        format_hint: Optional[str] = None,
    ) -> str:
        """Synthesize a narrative from structured data.

        Args:
            question: The user's original question.
            intent: Detected intent (dossier, compare, landscape, etc.).
            entity_info: Primary entity details (name, type, properties).
            metrics: Relevant KPIs (pipeline, success rate, etc.).
            graph_summary: Graph neighborhood summary.
            evidence_snippets: Top evidence text snippets.
            extra_context: Any additional context string.
            fallback_narrative: Template narrative to return if LLM is unavailable.
            format_hint: Optional "table" or "chart" to adjust prompt style.

        Returns:
            Synthesized narrative string.
        """
        if not self.enabled:
            return fallback_narrative

        ctx_mode = getattr(self.config.llm, "ctx_mode", "ctx")
        context = _build_context_block(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
            ctx_mode=ctx_mode,
        )

        system_prompt = _get_system_prompt(intent, format_hint)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        primary_model = self.config.llm.model
        fallback_model = getattr(self.config.llm, "fallback_model", primary_model)
        models = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models.append(fallback_model)

        client = self._get_client()
        import time as _time
        _t0 = _time.perf_counter()
        _last_err = None
        _prompt_text = system_prompt + "\n" + context
        # C1 depth: resolve the prompt_id for the exact system prompt used, so
        # the llm_call_log row carries a non-null prompt_id.
        _prompt_id = _resolve_synthesis_prompt_id(self._db, intent, format_hint)
        for model in models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=self.config.llm.max_tokens,
                    temperature=self.config.llm.temperature,
                )
                narrative = response.choices[0].message.content.strip()
                if narrative:
                    if model != primary_model:
                        logger.info("Used fallback model %s (primary unavailable)", model)
                    # C1: log the successful synthesis call before post-validation
                    # (which only edits the text, not whether the call happened).
                    self._log_call(
                        caller=f"llm.synthesize:{intent}", model=model,
                        prompt_text=_prompt_text, completion_text=narrative,
                        latency_ms=int((_time.perf_counter() - _t0) * 1000),
                        succeeded=True, prompt_id=_prompt_id,
                    )
                    # Post-synthesis validation
                    source_nums = _extract_source_numbers(metrics, evidence_snippets)
                    narrative = self._post_validate(
                        narrative,
                        evidence_count=len(evidence_snippets or []),
                        source_numbers=source_nums,
                        question=question,
                        evidence_text="\n".join(str(s) for s in (evidence_snippets or [])),
                    )
                    return narrative
            except Exception as e:
                _last_err = e
                logger.warning("Model %s failed: %s", model, e)
                continue

        self._log_call(
            caller=f"llm.synthesize:{intent}", model=(models[-1] if models else None),
            prompt_text=_prompt_text, completion_text=None,
            latency_ms=int((_time.perf_counter() - _t0) * 1000),
            succeeded=False, error=_last_err, prompt_id=_prompt_id,
        )
        return fallback_narrative

    def synthesize_stream(
        self,
        question: str,
        intent: str,
        entity_info: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        format_hint: Optional[str] = None,
    ):
        """Stream synthesis tokens. Yields str chunks. Falls back to empty if LLM unavailable."""
        if not self.enabled:
            return

        ctx_mode = getattr(self.config.llm, "ctx_mode", "ctx")
        context = _build_context_block(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
            ctx_mode=ctx_mode,
        )

        system_prompt = _get_system_prompt(intent, format_hint)

        try:
            client = self._get_client()
            stream = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context},
                ],
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.warning("LLM stream failed: %s", e)

    def synthesize_dossier(
        self,
        question: str,
        entity_name: str,
        entity_type: str,
        entity_details: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        fallback_narrative: str = "",
        extra_context: Optional[str] = None,
    ) -> str:
        """Specialized dossier synthesis."""
        entity_info = {
            "name": entity_name,
            "type": entity_type,
            **(entity_details or {}),
        }
        return self.synthesize(
            question=f"Tell me about {entity_name}",
            intent="dossier",
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            fallback_narrative=fallback_narrative,
            extra_context=extra_context,
        )

    def synthesize_comparison(
        self,
        entity_names: list[str],
        metrics_by_entity: Optional[dict] = None,
        shared_connections: Optional[list] = None,
        unique_connections: Optional[dict] = None,
        fallback_narrative: str = "",
        computed_insights: str = "",
        extra_context: Optional[str] = None,
    ) -> str:
        """Specialized comparison synthesis."""
        extra = ""
        if shared_connections:
            shared_labels = [c.get("label", c.get("entity_id", "?")) for c in shared_connections[:10]]
            extra += f"Shared connections ({len(shared_connections)}): {', '.join(shared_labels)}. "
        if unique_connections:
            for eid, conns in unique_connections.items():
                labels = [c.get("label", "?") for c in conns[:5]]
                extra += f"Unique to {eid}: {', '.join(labels)}. "
        if computed_insights:
            extra += f"\n{computed_insights}"
        if extra_context:
            extra += f"\n\nPRIOR CONVERSATION:\n{extra_context}"

        return self.synthesize(
            question=f"Compare {' vs '.join(entity_names)}",
            intent="compare",
            metrics=metrics_by_entity,
            extra_context=extra if extra else None,
            fallback_narrative=fallback_narrative,
        )

    def synthesize_landscape(
        self,
        question: str,
        segments: Optional[list[dict]] = None,
        fallback_narrative: str = "",
    ) -> str:
        """Specialized competitive landscape synthesis."""
        return self.synthesize(
            question=question,
            intent="landscape",
            metrics={"segments": segments or []},
            fallback_narrative=fallback_narrative,
        )

    def synthesize_pipeline(
        self,
        question: str,
        pipelines: Optional[list[dict]] = None,
        therapeutic_area: str = "",
        fallback_narrative: str = "",
    ) -> str:
        """Specialized pipeline synthesis."""
        return self.synthesize(
            question=question,
            intent="pipeline",
            metrics={"pipelines": pipelines or []},
            extra_context=f"Therapeutic area focus: {therapeutic_area}" if therapeutic_area else None,
            fallback_narrative=fallback_narrative,
        )

    def synthesize_research_report(
        self,
        question: str,
        graph_summary: Optional[dict] = None,
        metrics: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        web_results: Optional[list[dict]] = None,
        fallback_report: str = "",
    ) -> str:
        """Generate a deep-research brief with optional web augmentation."""
        if not self.enabled:
            return fallback_report

        extra_context = None
        if web_results:
            extra_context = f"WEB RESULTS: {json.dumps(web_results[:8], default=str)}"

        context = _build_context_block(
            question=question,
            intent="deep_research",
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
        )

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{context}\n\n"
                            "Write sections titled:\n"
                            "1) Executive Summary\n"
                            "2) Internal Evidence (Knowledge Graph)\n"
                            "3) Quantitative Signals\n"
                            "4) External Context (Web)\n"
                            "5) Risks and Data Gaps\n"
                            "6) Recommended Next Questions\n"
                            "Only include section 4 if web results are provided."
                        ),
                    },
                ],
                max_tokens=min(self.config.llm.max_tokens * 2, 2200),
                temperature=min(max(self.config.llm.temperature, 0.2), 0.5),
            )
            narrative = response.choices[0].message.content.strip()
            if narrative:
                return narrative
            return fallback_report
        except Exception as e:
            logger.warning("LLM research synthesis failed, using fallback: %s", e)
            return fallback_report
