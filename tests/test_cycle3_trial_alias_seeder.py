"""Cycle 3 — Trial acronym alias seeder (A3.2).

CT.gov returns each trial's identifierModule with:
  - acronym                              (e.g. "CHECKMATE-816")
  - orgStudyIdInfo.id                    (sponsor protocol id, e.g. "CA209-816")
  - secondaryIdInfos: [{id, type, ...}]  (EudraCT, IND, NCI, ISRCTN, etc.)

Press releases / news / 8-Ks routinely refer to trials by ANY of those
identifiers, not the NCT id. Seeding entity_aliases lets the
6-strategy entity_resolver match on first pass instead of falling
through to fuzzy + LLM.

Idempotency: entity_aliases has UNIQUE (entity_type, alias_text,
source_type). The seeder uses INSERT ... ON CONFLICT DO NOTHING so
re-runs are safe.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest


# ────────────────────────────────────────────────────────────────────
# Mock DB
# ────────────────────────────────────────────────────────────────────


class MockDB:
    def __init__(self):
        self.trials_by_nct: dict[str, dict] = {}
        self.aliases: list[dict] = []
        self.executed: list[tuple[str, list]] = []

    def fetch_one(self, query: str, params=None):
        self.executed.append((query, params))
        q = query.lower()
        if "from clinical_trials" in q and "nct_id" in q:
            return self.trials_by_nct.get(params[0] if params else None)
        if "insert into entity_aliases" in q:
            entity_type, entity_id, alias_text, source_type, confidence, *_ = params
            # Simulate ON CONFLICT — duplicate skipped
            for a in self.aliases:
                if (a["entity_type"] == entity_type
                        and a["alias_text"] == alias_text
                        and a["source_type"] == source_type):
                    return None
            new_row = {
                "id": "00000000-0000-0000-0000-{:012d}".format(
                    len(self.aliases) + 1),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "alias_text": alias_text,
                "source_type": source_type,
                "confidence": confidence,
            }
            self.aliases.append(new_row)
            return {"id": new_row["id"]}
        return None

    def execute(self, query: str, params=None):
        self.executed.append((query, params))


@pytest.fixture
def mock_db():
    return MockDB()


def _seed_trial(
    db: MockDB,
    nct_id: str,
    trial_id: str = "00000000-0000-0000-0000-aaaaaaaaaaaa",
):
    db.trials_by_nct[nct_id] = {"id": trial_id, "nct_id": nct_id}


def _study(nct_id: str, **kwargs) -> dict:
    """Build a minimal CT.gov study payload for tests."""
    ident = {
        "nctId": nct_id,
        "acronym": kwargs.get("acronym"),
        "briefTitle": kwargs.get("brief_title", "A trial"),
    }
    if "org_study_id" in kwargs:
        ident["orgStudyIdInfo"] = {"id": kwargs["org_study_id"]}
    if "secondary_ids" in kwargs:
        ident["secondaryIdInfos"] = [
            {"id": s.get("id"), "type": s.get("type", "OTHER_GRANT")}
            for s in kwargs["secondary_ids"]
        ]
    return {
        "protocolSection": {
            "identificationModule": ident,
        }
    }


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Module exists
# ────────────────────────────────────────────────────────────────────


class TestModuleExists:

    def test_module_imports(self):
        from services.trial_alias_seeder import seed_aliases_from_study  # noqa: F401

    def test_seed_result_dataclass(self):
        from services.trial_alias_seeder import SeedResult
        r = SeedResult()
        assert r.aliases_inserted == 0
        assert r.aliases_skipped == 0
        assert r.skipped_reason is None


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Trial resolution
# ────────────────────────────────────────────────────────────────────


class TestTrialResolution:

    def test_unknown_nct_id_returns_skipped(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        result = seed_aliases_from_study(
            study=_study("NCT99999", acronym="ZEROBASE"),
            db=mock_db,
        )
        assert result.aliases_inserted == 0
        assert result.skipped_reason == "trial_not_found"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Acronym extraction
# ────────────────────────────────────────────────────────────────────


class TestAcronymExtraction:

    def test_acronym_seeded(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT100")
        result = seed_aliases_from_study(
            study=_study("NCT100", acronym="CHECKMATE-816"),
            db=mock_db,
        )
        assert result.aliases_inserted == 1
        a = mock_db.aliases[0]
        assert a["entity_type"] == "trial"
        assert a["alias_text"] == "CHECKMATE-816"
        assert a["source_type"] == "ctgov_acronym"

    def test_empty_acronym_skipped(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT101")
        result = seed_aliases_from_study(
            study=_study("NCT101", acronym=""),
            db=mock_db,
        )
        assert result.aliases_inserted == 0


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Sponsor protocol id (orgStudyIdInfo)
# ────────────────────────────────────────────────────────────────────


class TestSponsorProtocolId:

    def test_org_study_id_seeded(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT200")
        result = seed_aliases_from_study(
            study=_study("NCT200", org_study_id="CA209-816"),
            db=mock_db,
        )
        assert result.aliases_inserted == 1
        a = mock_db.aliases[0]
        assert a["alias_text"] == "CA209-816"
        assert a["source_type"] == "ctgov_org_study_id"


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Secondary IDs (EudraCT, IND, ISRCTN, etc.)
# ────────────────────────────────────────────────────────────────────


class TestSecondaryIds:

    def test_eudract_seeded_with_typed_source(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT300")
        result = seed_aliases_from_study(
            study=_study("NCT300", secondary_ids=[
                {"id": "2024-500123-15", "type": "EUDRACT_NUMBER"},
            ]),
            db=mock_db,
        )
        assert result.aliases_inserted == 1
        a = mock_db.aliases[0]
        assert a["alias_text"] == "2024-500123-15"
        assert a["source_type"].startswith("ctgov_secondary_")

    def test_multiple_secondary_ids_all_seeded(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT301")
        result = seed_aliases_from_study(
            study=_study("NCT301", secondary_ids=[
                {"id": "EUCTR-1", "type": "EUDRACT_NUMBER"},
                {"id": "ISRCTN12345", "type": "REGISTRY"},
                {"id": "IND-123", "type": "OTHER_GRANT"},
            ]),
            db=mock_db,
        )
        assert result.aliases_inserted == 3


# ────────────────────────────────────────────────────────────────────
# Cat 6 — Combined (acronym + org id + secondaries)
# ────────────────────────────────────────────────────────────────────


class TestCombined:

    def test_full_payload_seeds_all(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT400")
        result = seed_aliases_from_study(
            study=_study("NCT400",
                         acronym="DESTINY-Breast04",
                         org_study_id="DS8201-A-U302",
                         secondary_ids=[
                             {"id": "2019-002113-22",
                              "type": "EUDRACT_NUMBER"},
                         ]),
            db=mock_db,
        )
        assert result.aliases_inserted == 3
        alias_texts = [a["alias_text"] for a in mock_db.aliases]
        assert "DESTINY-Breast04" in alias_texts
        assert "DS8201-A-U302" in alias_texts
        assert "2019-002113-22" in alias_texts


# ────────────────────────────────────────────────────────────────────
# Cat 7 — Idempotency
# ────────────────────────────────────────────────────────────────────


class TestIdempotency:

    def test_rerun_is_safe(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT500")
        study = _study("NCT500", acronym="RAINFOREST",
                       org_study_id="MK-1234-001")

        r1 = seed_aliases_from_study(study=study, db=mock_db)
        assert r1.aliases_inserted == 2
        assert r1.aliases_skipped == 0

        r2 = seed_aliases_from_study(study=study, db=mock_db)
        assert r2.aliases_inserted == 0
        assert r2.aliases_skipped == 2

        # Total alias rows in DB unchanged
        assert len(mock_db.aliases) == 2


# ────────────────────────────────────────────────────────────────────
# Cat 8 — Edge cases
# ────────────────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_no_identifiers_returns_zero(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT600")
        result = seed_aliases_from_study(
            study=_study("NCT600"),  # only nct_id, no acronym/org/secondaries
            db=mock_db,
        )
        assert result.aliases_inserted == 0
        assert result.aliases_skipped == 0

    def test_alias_equal_to_nct_id_is_dropped(self, mock_db):
        """Don't seed the NCT id as an alias of itself — entity_resolver
        already keys off nct_id directly."""
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT700")
        result = seed_aliases_from_study(
            study=_study("NCT700", acronym="NCT700"),
            db=mock_db,
        )
        assert result.aliases_inserted == 0

    def test_short_alias_ignored(self, mock_db):
        """Aliases of < 3 chars are not useful for matching."""
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT800")
        result = seed_aliases_from_study(
            study=_study("NCT800", acronym="X1"),
            db=mock_db,
        )
        assert result.aliases_inserted == 0

    def test_whitespace_normalised(self, mock_db):
        from services.trial_alias_seeder import seed_aliases_from_study
        _seed_trial(mock_db, "NCT900")
        result = seed_aliases_from_study(
            study=_study("NCT900", acronym="  CHECKMATE-001  "),
            db=mock_db,
        )
        assert result.aliases_inserted == 1
        assert mock_db.aliases[0]["alias_text"] == "CHECKMATE-001"
