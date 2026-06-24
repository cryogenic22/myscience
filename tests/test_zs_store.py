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
