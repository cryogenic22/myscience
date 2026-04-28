"""Company identity helpers — alias dedup + external-id authority merge.

SPEC-016 §7 swimlane A1.1. Used by:
  - entity_resolver alias cascade (read aliases for fuzzy/exact match)
  - connectors during ingest (write new aliases / external_ids without
    clobbering authoritative existing values)
  - the data steward when consolidating duplicate company rows

Two functions:

  merge_aliases(existing, new)
    Returns a deduplicated alias list. Dedup is case-insensitive after
    normalising legal suffixes (Inc., Corp., Ltd., …) and whitespace,
    BUT preserves all distinct surface forms in the output (so the
    resolver can match on whatever form a press release used).

  merge_external_ids(existing, new)
    Returns a single external_ids bag where each key resolves via the
    SOURCE_AUTHORITY ranking. List-valued keys are unioned (e.g.
    openfda_labeler_codes). Sibling _source_<key> records track which
    connector wrote each value.
"""

from __future__ import annotations

import re

# ────────────────────────────────────────────────────────────────────
# Authority ranking for conflict resolution on external_ids
# ────────────────────────────────────────────────────────────────────

# Higher rank wins on conflict. Add new sources with explicit rank;
# unknown sources rank 0 (always lose to any known source).
_SOURCE_AUTHORITY: dict[str, int] = {
    "sec_edgar":      100,  # primary source for cik, ticker, lei
    "openfda":         90,  # authoritative for openfda_labeler_codes
    "gleif":           90,  # authoritative for lei
    "rxnorm":          80,
    "cortellis":       70,
    "evaluate_pharma": 70,
    "pitchbook":       60,
    "manual":          50,  # human curation, mid-rank (overridable by primary sources)
    "user_tagged":     50,
    "news":            30,
    "press":           30,
    "default_pre_calibration": 10,
}


def _authority(source: str | None) -> int:
    if not source:
        return 0
    return _SOURCE_AUTHORITY.get(source, 0)


# ────────────────────────────────────────────────────────────────────
# Alias dedup
# ────────────────────────────────────────────────────────────────────

# Common legal suffixes — stripped only for dedup comparison, not from the
# stored value. Order matters (multi-word first).
_LEGAL_SUFFIX_RE = re.compile(
    r"\s+(?:plc|inc|corp|corporation|company|co|ltd|limited|llc|gmbh|"
    r"sa|s\.a\.|s\.l\.|nv|n\.v\.|kk|k\.k\.|ag|spa|s\.p\.a\.|holdings|"
    r"pharmaceuticals|pharma|biosciences|biotech|therapeutics)\.?\s*$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalise_for_dedup(alias: str) -> str:
    """Lowercase, strip legal suffix, collapse whitespace, strip trailing dots."""
    s = (alias or "").lower().strip()
    s = _WHITESPACE_RE.sub(" ", s)
    s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    s = s.rstrip(".").strip()
    return s


def merge_aliases(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Dedupe aliases case-insensitively after normalising legal suffixes.

    Preserves distinct surface forms — `Pfizer` and `Pfizer Inc.` both
    survive even though they normalise the same way (so the resolver can
    match either form against incoming text).

    Empty / None alias strings are dropped.

    Order: existing first (preserves seniority), then new (newer additions
    appended).
    """
    out: list[str] = []
    seen_surface: set[str] = set()  # stripped, case-preserved
    seen_normalised: dict[str, list[str]] = {}  # norm → list of surface forms kept

    for alias in (existing or []) + (new or []):
        if not alias:
            continue
        surface = _WHITESPACE_RE.sub(" ", alias.strip())
        if not surface:
            continue
        if surface in seen_surface:
            continue  # exact same surface form already kept
        seen_surface.add(surface)

        norm = _normalise_for_dedup(surface)
        if not norm:
            # Pure punctuation / suffix-only — drop
            continue

        # Always keep the first canonical "Inc."-form for a normalised group;
        # also keep any DIFFERENT surface form (e.g. without suffix).
        if norm not in seen_normalised:
            out.append(surface)
            seen_normalised[norm] = [surface]
        else:
            # Same normalised form — keep ONLY if surface differs meaningfully
            # from prior surface. "Different" means different casing AND
            # different content after stripping trailing dots/whitespace.
            # `Pfizer Inc.` and `Pfizer Inc` are the SAME (drop the second);
            # `Pfizer Inc.` and `Pfizer` are different (keep both).
            def _surface_key(s: str) -> str:
                return s.lower().rstrip(".").strip()

            this_key = _surface_key(surface)
            prior_keys = [_surface_key(p) for p in seen_normalised[norm]]
            if this_key not in prior_keys:
                out.append(surface)
                seen_normalised[norm].append(surface)

    return out


# ────────────────────────────────────────────────────────────────────
# external_ids merge with authority-based conflict resolution
# ────────────────────────────────────────────────────────────────────

# Keys whose values are LISTS (union semantics on conflict)
_LIST_VALUED_KEYS = frozenset({
    "openfda_labeler_codes",
    "ticker_aliases",
    "former_ciks",
})


def merge_external_ids(
    existing: dict | None,
    new: dict | None,
) -> dict:
    """Merge two external_ids bags.

    Conflict rule for scalar keys: the value backed by the higher-authority
    source wins. Authority is read from the sibling `_source_<key>` field
    in either input bag; if absent, treated as authority 0.

    Conflict rule for list-valued keys (in _LIST_VALUED_KEYS): values are
    unioned. _source_<key> on a list key is preserved from the input that
    contributed the most values; ties broken by `existing` winning.

    `_source_<key>` tracking fields are propagated alongside their values.
    """
    existing = dict(existing or {})
    new = dict(new or {})

    out: dict = {}

    # Collect all keys (excluding _source_* meta keys, handled with their value)
    all_keys = (
        {k for k in existing if not k.startswith("_source_")}
        | {k for k in new if not k.startswith("_source_")}
    )

    for key in all_keys:
        in_existing = key in existing and existing[key] is not None
        in_new = key in new and new[key] is not None

        existing_source = existing.get(f"_source_{key}")
        new_source = new.get(f"_source_{key}")

        if key in _LIST_VALUED_KEYS:
            # Union semantics
            ex_list = list(existing.get(key) or [])
            nw_list = list(new.get(key) or [])
            merged = list(dict.fromkeys(ex_list + nw_list))  # preserves order, dedups
            out[key] = merged
            # Source: whichever contributed more values; tie → existing
            if len(nw_list) > len(ex_list) and new_source:
                out[f"_source_{key}"] = new_source
            elif existing_source:
                out[f"_source_{key}"] = existing_source
            elif new_source:
                out[f"_source_{key}"] = new_source
            continue

        # Scalar key
        if in_existing and not in_new:
            out[key] = existing[key]
            if existing_source:
                out[f"_source_{key}"] = existing_source
        elif in_new and not in_existing:
            out[key] = new[key]
            if new_source:
                out[f"_source_{key}"] = new_source
        elif in_existing and in_new:
            # Conflict — authority decides
            if _authority(existing_source) >= _authority(new_source):
                out[key] = existing[key]
                if existing_source:
                    out[f"_source_{key}"] = existing_source
            else:
                out[key] = new[key]
                if new_source:
                    out[f"_source_{key}"] = new_source

    return out
