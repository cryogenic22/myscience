"""DB-free tests for the file-backed ZS capability-card store.

Every test points ``ZS_DATA_DIR`` at a pytest ``tmp_path`` so nothing touches
the repo's ``static/zs/data`` dir. Covers: seed-on-missing, atomic round-trip,
CRUD, duplicate-id rejection, import validation, export shape.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from services import zs_store


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Isolate every test to a fresh tmp data dir, with no Railway var bleed-through."""
    monkeypatch.setenv("ZS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    return tmp_path


# --- seeding ---------------------------------------------------------------
def test_load_seeds_file_when_missing(isolated_data_dir):
    f = zs_store.data_file()
    assert not f.exists()  # nothing yet
    cards = zs_store.load()
    assert f.exists()  # load() seeded it
    # the canonical six LIBRARY cards
    assert len(cards) == len(zs_store.DEFAULT_CARDS) == 6
    ids = {c.id for c in cards}
    assert {"decisionops", "devreg", "cognitive", "platform", "trust", "cliff"} == ids


def test_seed_carries_moat_scores(isolated_data_dir):
    cards = {c.id: c for c in zs_store.load()}
    # decisionops moats from OFFERING_MOATS
    m = cards["decisionops"].moats
    assert (m.ground, m.compliance, m.switching, m.trust, m.convenience) == (3, 2, 3, 2, 2)


def test_data_dir_prefers_explicit_over_railway(monkeypatch, tmp_path):
    monkeypatch.setenv("ZS_DATA_DIR", str(tmp_path / "explicit"))
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "railway"))
    assert zs_store.data_dir() == (tmp_path / "explicit")


def test_data_dir_falls_back_to_railway(monkeypatch, tmp_path):
    monkeypatch.delenv("ZS_DATA_DIR", raising=False)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "vol"))
    assert zs_store.data_dir() == (tmp_path / "vol")


# --- atomic round-trip -----------------------------------------------------
def test_atomic_write_round_trips_and_leaves_no_tmp(isolated_data_dir):
    zs_store.load()  # seed
    new = zs_store.CapabilityCard(name="Round trip", pool="ai", model="hybrid", size=0.4, start=2, attain=50)
    zs_store.create(new)
    # on-disk JSON parses and reflects the create
    raw = json.loads(zs_store.data_file().read_text(encoding="utf-8"))
    assert any(c["name"] == "Round trip" for c in raw["cards"])
    # no leftover *.tmp-* files
    leftovers = list(isolated_data_dir.glob("*.tmp-*"))
    assert leftovers == []


# --- create ----------------------------------------------------------------
def test_create_assigns_slug_id_when_absent(isolated_data_dir):
    zs_store.load()
    created = zs_store.create(
        zs_store.CapabilityCard(name="My New Cap!", pool="rnd", model="perunit", size=0.3, start=1, attain=40)
    )
    assert created.id == "my-new-cap"
    assert zs_store.get("my-new-cap") is not None


def test_create_rejects_duplicate_id(isolated_data_dir):
    zs_store.load()
    with pytest.raises(ValueError, match="already exists"):
        zs_store.create(
            zs_store.CapabilityCard(id="decisionops", name="dup", pool="ai", model="hybrid", size=0.1, start=1, attain=10)
        )


# --- update ----------------------------------------------------------------
def test_update_existing_card(isolated_data_dir):
    zs_store.load()
    updated = zs_store.update(
        "platform",
        zs_store.CapabilityCard(name="Platform v2", pool="ai", model="subusage", size=0.5, start=2, attain=70),
    )
    assert updated is not None
    assert updated.id == "platform"  # path id wins
    assert updated.name == "Platform v2"
    assert zs_store.get("platform").size == 0.5


def test_update_missing_returns_none(isolated_data_dir):
    zs_store.load()
    res = zs_store.update(
        "nope", zs_store.CapabilityCard(name="x", pool="ai", model="hybrid", size=0.1, start=1, attain=10)
    )
    assert res is None


# --- delete ----------------------------------------------------------------
def test_delete_existing(isolated_data_dir):
    zs_store.load()
    assert zs_store.delete("cliff") is True
    assert zs_store.get("cliff") is None
    assert len(zs_store.load()) == 5


def test_delete_missing_returns_false(isolated_data_dir):
    zs_store.load()
    assert zs_store.delete("nope") is False
    assert len(zs_store.load()) == 6


# --- validation ------------------------------------------------------------
def test_unknown_pool_rejected():
    with pytest.raises(ValidationError):
        zs_store.CapabilityCard(name="bad", pool="nonsense", model="hybrid", size=0.1, start=1, attain=10)


def test_unknown_model_rejected():
    with pytest.raises(ValidationError):
        zs_store.CapabilityCard(name="bad", pool="ai", model="nonsense", size=0.1, start=1, attain=10)


def test_size_and_attain_bounds():
    with pytest.raises(ValidationError):
        zs_store.CapabilityCard(name="bad", pool="ai", model="hybrid", size=1.5, start=1, attain=10)
    with pytest.raises(ValidationError):
        zs_store.CapabilityCard(name="bad", pool="ai", model="hybrid", size=0.5, start=1, attain=150)


def test_moat_scores_bounds():
    with pytest.raises(ValidationError):
        zs_store.CapabilityCard(
            name="bad", pool="ai", model="hybrid", size=0.5, start=1, attain=50, moats={"ground": 5}
        )


# --- import / export -------------------------------------------------------
def test_export_shape(isolated_data_dir):
    out = zs_store.export_dict()
    assert set(out.keys()) == {"cards"}
    assert isinstance(out["cards"], list) and len(out["cards"]) == 6
    card = out["cards"][0]
    for key in ("id", "name", "pool", "model", "size", "start", "attain", "moats"):
        assert key in card


def test_replace_all_validates_and_replaces(isolated_data_dir):
    zs_store.load()
    payload = {
        "cards": [
            {"name": "Only One", "pool": "governance", "model": "assurance", "size": 0.2, "start": 3, "attain": 55},
        ]
    }
    result = zs_store.replace_all(payload)
    assert len(result) == 1
    assert result[0].id == "only-one"
    assert len(zs_store.load()) == 1


def test_replace_all_rejects_bad_card_without_writing(isolated_data_dir):
    zs_store.load()
    before = zs_store.export_dict()
    with pytest.raises(ValidationError):
        zs_store.replace_all({"cards": [{"name": "x", "pool": "BAD", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}]})
    # file unchanged — validation failed before _save
    assert zs_store.export_dict() == before


def test_replace_all_rejects_malformed_payload(isolated_data_dir):
    with pytest.raises(ValueError, match="cards"):
        zs_store.replace_all({"not_cards": []})


def test_replace_all_rejects_duplicate_ids(isolated_data_dir):
    payload = {
        "cards": [
            {"id": "dup", "name": "a", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10},
            {"id": "dup", "name": "b", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10},
        ]
    }
    with pytest.raises(ValueError, match="duplicate"):
        zs_store.replace_all(payload)


# --- review NIT fixes ------------------------------------------------------
def test_corrupt_file_self_heals_and_preserves_bytes(isolated_data_dir):
    """A corrupt data file must not 500 every read: it is quarantined (bytes
    preserved) and the store re-seeds, so reads recover."""
    zs_store.load()  # seed a valid file first
    f = zs_store.data_file()
    f.write_text("{ this is not valid json", encoding="utf-8")  # corrupt it

    cards = zs_store.load()  # must NOT raise — self-heals
    assert len(cards) == 6  # re-seeded to the canonical defaults

    # the corrupt bytes are preserved (not silently discarded), recoverable
    backups = list(isolated_data_dir.glob("capability_cards.json.corrupt*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ this is not valid json"


def test_corrupt_file_with_wrong_shape_also_self_heals(isolated_data_dir):
    """Parseable JSON but wrong shape ({} instead of {'cards': [...]}) self-heals too."""
    zs_store.load()
    zs_store.data_file().write_text('{"nope": 1}', encoding="utf-8")
    cards = zs_store.load()
    assert len(cards) == 6
    assert list(isolated_data_dir.glob("capability_cards.json.corrupt*"))


def test_import_over_card_limit_rejected_without_writing(isolated_data_dir):
    """An oversized import is rejected before any write (auth-gated DoS guard)."""
    zs_store.load()
    before = zs_store.export_dict()
    too_many = {
        "cards": [
            {"name": f"c{i}", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}
            for i in range(zs_store._MAX_IMPORT_CARDS + 1)
        ]
    }
    with pytest.raises(ValueError, match="limit"):
        zs_store.replace_all(too_many)
    assert zs_store.export_dict() == before  # nothing written


# ===========================================================================
# Two new card FAMILIES — commercial constructs + capability bets.
# They ride the identical store machinery via a `family` argument; these tests
# cover the seed substance, CRUD, enum validation, per-family file isolation,
# the shared corrupt-self-heal and the shared import bound.
# ===========================================================================

# --- registry --------------------------------------------------------------
def test_families_registry_lists_three():
    assert zs_store.families() == ("cards", "constructs", "bets")


def test_unknown_family_rejected(isolated_data_dir):
    with pytest.raises(ValueError, match="unknown card family"):
        zs_store.load("nonsense")
    with pytest.raises(ValueError, match="unknown card family"):
        zs_store.data_file("nonsense")


def test_each_family_uses_its_own_file(isolated_data_dir):
    assert zs_store.data_file("cards").name == "capability_cards.json"
    assert zs_store.data_file("constructs").name == "commercial_constructs.json"
    assert zs_store.data_file("bets").name == "capability_bets.json"


# --- constructs: seed substance --------------------------------------------
def test_constructs_seed_contents(isolated_data_dir):
    f = zs_store.data_file("constructs")
    assert not f.exists()
    cards = zs_store.load("constructs")
    assert f.exists()  # seeded on first load
    assert len(cards) == len(zs_store.DEFAULT_CONSTRUCTS) == 6
    by_id = {c.id: c for c in cards}
    assert set(by_id) == {
        "floor-per-hit", "decision-latency-sla", "gain-share",
        "cost-to-serve-takeout", "assurance-per-cert", "outcome-underwriting",
    }
    # verbatim substance is preserved (not paraphrased)
    fph = by_id["floor-per-hit"]
    assert fph.name == "Floor + per-hit"
    assert fph.quality == "outcome"
    assert fph.meter == "A discrete, pre-agreed outcome event ('a hit')"
    assert "success fee fires per realized outcome event" in fph.value_story
    assert by_id["decision-latency-sla"].quality == "recurring"
    assert by_id["cost-to-serve-takeout"].quality == "project"


# --- bets: seed substance --------------------------------------------------
def test_bets_seed_contents(isolated_data_dir):
    f = zs_store.data_file("bets")
    assert not f.exists()
    cards = zs_store.load("bets")
    assert f.exists()
    assert len(cards) == len(zs_store.DEFAULT_BETS) == 6
    by_id = {c.id: c for c in cards}
    assert set(by_id) == {
        "simulation-aas", "digital-twin", "pharma-slms",
        "the-harness", "quantum", "hardware-edge",
    }
    harness = by_id["the-harness"]
    assert harness.name == "The Harness (governance standard)"
    assert harness.horizon == "moonshot"
    assert harness.posture == "build"
    assert harness.native is True
    assert "tollbooth" in harness.thesis
    # quantum + hardware are explicitly NOT native ZS builds
    assert by_id["quantum"].native is False
    assert by_id["quantum"].posture == "partner"
    assert by_id["hardware-edge"].native is False
    assert by_id["hardware-edge"].posture == "consume"
    assert by_id["simulation-aas"].horizon == "near"


# --- per-family isolation: editing one does not touch another --------------
def test_families_are_independent(isolated_data_dir):
    zs_store.load("cards")
    zs_store.load("constructs")
    zs_store.load("bets")
    # delete from constructs only
    assert zs_store.delete("gain-share", "constructs") is True
    assert len(zs_store.load("constructs")) == 5
    # cards + bets untouched
    assert len(zs_store.load("cards")) == 6
    assert len(zs_store.load("bets")) == 6


# --- constructs CRUD round-trip --------------------------------------------
def test_constructs_crud_round_trip(isolated_data_dir):
    zs_store.load("constructs")
    created = zs_store.create(
        zs_store.ConstructCard(name="Retainer Plus", quality="recurring", meter="monthly"),
        "constructs",
    )
    assert created.id == "retainer-plus"
    assert zs_store.get("retainer-plus", "constructs") is not None
    updated = zs_store.update(
        "retainer-plus",
        zs_store.ConstructCard(name="Retainer Pro", quality="outcome"),
        "constructs",
    )
    assert updated is not None and updated.id == "retainer-plus" and updated.name == "Retainer Pro"
    assert zs_store.delete("retainer-plus", "constructs") is True
    assert zs_store.get("retainer-plus", "constructs") is None
    # update/delete of a missing id behave like cards
    assert zs_store.update("nope", zs_store.ConstructCard(name="x"), "constructs") is None
    assert zs_store.delete("nope", "constructs") is False


# --- bets CRUD round-trip --------------------------------------------------
def test_bets_crud_round_trip(isolated_data_dir):
    zs_store.load("bets")
    created = zs_store.create(
        zs_store.BetCard(name="Edge Inference", horizon="near", posture="build", native=False),
        "bets",
    )
    assert created.id == "edge-inference"
    assert created.native is False
    updated = zs_store.update(
        "edge-inference", zs_store.BetCard(name="Edge Inference v2", posture="partner"), "bets"
    )
    assert updated is not None and updated.posture == "partner"
    assert zs_store.delete("edge-inference", "bets") is True
    assert zs_store.update("nope", zs_store.BetCard(name="x"), "bets") is None
    assert zs_store.delete("nope", "bets") is False


# --- light validation: empty enums allowed, bad enums rejected -------------
def test_construct_empty_quality_allowed():
    # prose-holding card: blank enum is the "unset" default and is fine
    c = zs_store.ConstructCard(name="Sketch")
    assert c.quality == ""


def test_construct_bad_quality_rejected():
    with pytest.raises(ValidationError):
        zs_store.ConstructCard(name="bad", quality="nonsense")


def test_bet_empty_enums_allowed():
    b = zs_store.BetCard(name="Sketch")
    assert b.horizon == "" and b.posture == "" and b.native is True


def test_bet_bad_horizon_rejected():
    with pytest.raises(ValidationError):
        zs_store.BetCard(name="bad", horizon="someday")


def test_bet_bad_posture_rejected():
    with pytest.raises(ValidationError):
        zs_store.BetCard(name="bad", posture="acquire")


def test_construct_requires_name():
    with pytest.raises(ValidationError):
        zs_store.ConstructCard(name="")


def test_bet_requires_name():
    with pytest.raises(ValidationError):
        zs_store.BetCard(name="")


# --- export shape per family -----------------------------------------------
def test_export_shape_constructs(isolated_data_dir):
    out = zs_store.export_dict("constructs")
    assert set(out.keys()) == {"cards"}
    assert len(out["cards"]) == 6
    for key in ("id", "name", "meter", "value_story", "quality", "buyer", "zs_risk", "fit", "examples"):
        assert key in out["cards"][0]


def test_export_shape_bets(isolated_data_dir):
    out = zs_store.export_dict("bets")
    assert set(out.keys()) == {"cards"}
    assert len(out["cards"]) == 6
    for key in ("id", "name", "thesis", "unit_moat", "kill_criterion", "ceiling", "horizon", "posture", "native"):
        assert key in out["cards"][0]


# --- import validation per family ------------------------------------------
def test_constructs_replace_all_validates_and_replaces(isolated_data_dir):
    zs_store.load("constructs")
    result = zs_store.replace_all(
        {"cards": [{"name": "Only One", "quality": "outcome"}]}, "constructs"
    )
    assert len(result) == 1 and result[0].id == "only-one"
    assert len(zs_store.load("constructs")) == 1


def test_constructs_import_bad_enum_rejected_without_writing(isolated_data_dir):
    zs_store.load("constructs")
    before = zs_store.export_dict("constructs")
    with pytest.raises(ValidationError):
        zs_store.replace_all({"cards": [{"name": "x", "quality": "BAD"}]}, "constructs")
    assert zs_store.export_dict("constructs") == before


def test_bets_import_bad_enum_rejected_without_writing(isolated_data_dir):
    zs_store.load("bets")
    before = zs_store.export_dict("bets")
    with pytest.raises(ValidationError):
        zs_store.replace_all({"cards": [{"name": "x", "posture": "BAD"}]}, "bets")
    assert zs_store.export_dict("bets") == before


# --- the shared import bound applies to every family -----------------------
@pytest.mark.parametrize("family", ["constructs", "bets"])
def test_import_over_limit_rejected_per_family(isolated_data_dir, family):
    zs_store.load(family)
    before = zs_store.export_dict(family)
    too_many = {"cards": [{"name": f"c{i}"} for i in range(zs_store._MAX_IMPORT_CARDS + 1)]}
    with pytest.raises(ValueError, match="limit"):
        zs_store.replace_all(too_many, family)
    assert zs_store.export_dict(family) == before  # nothing written


# --- the shared corrupt-self-heal applies to every family ------------------
@pytest.mark.parametrize("family", ["cards", "constructs", "bets"])
def test_corrupt_file_self_heals_per_family(isolated_data_dir, family):
    zs_store.load(family)  # seed a valid file
    f = zs_store.data_file(family)
    f.write_text("{ not valid json", encoding="utf-8")
    cards = zs_store.load(family)  # must NOT raise — self-heals
    assert len(cards) == 6  # re-seeded to that family's defaults
    backups = list(isolated_data_dir.glob(f"{f.name}.corrupt*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ not valid json"  # bytes preserved
