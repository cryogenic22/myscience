"""Trial alias seeder — populates entity_aliases from CT.gov metadata.

SPEC-016 §7 swimlane A3.2 (Cycle 3).

CT.gov returns for every trial:

  protocolSection.identificationModule = {
    nctId:           "NCT01234567",
    acronym:         "CHECKMATE-816",          (optional)
    briefTitle:      "...",
    orgStudyIdInfo:  {id: "CA209-816", ...},   (sponsor protocol id)
    secondaryIdInfos:[                          (other registries / IND / NCI)
      {id: "2019-002113-22", type: "EUDRACT_NUMBER"},
      ...
    ]
  }

Press releases, news articles, 8-Ks, EMA decisions, etc. routinely
refer to a trial by ANY of those identifiers — rarely the NCT id.
Seeding entity_aliases gives the 6-strategy entity_resolver a
first-pass exact match instead of falling through to fuzzy + LLM.

Idempotency: entity_aliases has a UNIQUE index on
(entity_type, alias_text, source_type). The seeder uses
INSERT ... ON CONFLICT DO NOTHING so re-runs are safe.

Defensive filters:
  - alias_text equal to nct_id is dropped (the resolver already keys
    off nct_id; we'd just create a self-referential row)
  - alias_text < 3 chars is dropped (not specific enough to match on)
  - whitespace stripped from alias_text
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# SeedResult
# ────────────────────────────────────────────────────────────────────


@dataclass
class SeedResult:
    aliases_inserted: int = 0
    aliases_skipped: int = 0
    skipped_reason: Optional[str] = None
    nct_id: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# SQL
# ────────────────────────────────────────────────────────────────────


_TRIAL_LOOKUP_SQL = """
    SELECT id, nct_id
    FROM clinical_trials
    WHERE nct_id = %s
    LIMIT 1
"""

_ALIAS_INSERT_SQL = """
    INSERT INTO entity_aliases (
        entity_type, entity_id, alias_text, source_type, confidence, verified
    ) VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
    RETURNING id
"""


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


_MIN_ALIAS_LEN = 3


def _clean(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _is_seedable(text: Optional[str], nct_id: str) -> bool:
    if not text:
        return False
    if len(text) < _MIN_ALIAS_LEN:
        return False
    if text.upper() == nct_id.upper():
        return False
    return True


def _classify_secondary_source_type(raw_type: Optional[str]) -> str:
    """Map CT.gov secondaryIdInfos.type → entity_aliases.source_type.

    Keeps the registry name in the source_type so the resolver can
    weight EudraCT / ISRCTN / IND identifiers differently from generic
    "OTHER_GRANT" entries.
    """
    if not raw_type:
        return "ctgov_secondary_other"
    t = raw_type.strip().upper()
    if "EUDRA" in t:
        return "ctgov_secondary_eudract"
    if "ISRCTN" in t:
        return "ctgov_secondary_isrctn"
    if "REGISTRY" in t:
        return "ctgov_secondary_registry"
    if "NCI" in t:
        return "ctgov_secondary_nci"
    if "IND" in t or "FDA" in t:
        return "ctgov_secondary_fda"
    return "ctgov_secondary_other"


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def seed_aliases_from_study(*, study: dict, db: Any) -> SeedResult:
    """Extract aliases from a CT.gov study payload and INSERT into
    entity_aliases. Returns a SeedResult tally.
    """
    proto = study.get("protocolSection") or {}
    ident = proto.get("identificationModule") or {}
    nct_id = _clean(ident.get("nctId"))
    if not nct_id:
        return SeedResult(skipped_reason="missing_nct_id")

    trial_row = db.fetch_one(_TRIAL_LOOKUP_SQL, [nct_id])
    if not trial_row:
        return SeedResult(nct_id=nct_id, skipped_reason="trial_not_found")
    trial_id = str(trial_row.get("id") or "")

    candidates: list[tuple[str, str, float]] = []
    # (alias_text, source_type, confidence)

    acronym = _clean(ident.get("acronym"))
    if _is_seedable(acronym, nct_id):
        candidates.append((acronym, "ctgov_acronym", 0.98))

    org_info = ident.get("orgStudyIdInfo") or {}
    org_id = _clean(org_info.get("id"))
    if _is_seedable(org_id, nct_id):
        candidates.append((org_id, "ctgov_org_study_id", 0.95))

    for sec in ident.get("secondaryIdInfos") or []:
        sec_id = _clean(sec.get("id"))
        if _is_seedable(sec_id, nct_id):
            source_type = _classify_secondary_source_type(sec.get("type"))
            candidates.append((sec_id, source_type, 0.90))

    inserted = 0
    skipped = 0
    for alias_text, source_type, confidence in candidates:
        result = db.fetch_one(
            _ALIAS_INSERT_SQL,
            ["trial", trial_id, alias_text, source_type, confidence, False],
        )
        if result:
            inserted += 1
        else:
            skipped += 1

    return SeedResult(
        nct_id=nct_id,
        aliases_inserted=inserted,
        aliases_skipped=skipped,
    )
