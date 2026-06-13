"""BE-40 — system-prompts in prompt_registry tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

def test_migration_076_adds_is_active_column():
    sql = (Path(__file__).parent.parent / "schema" / "migrations"
           / "076_seed_system_prompts.sql").read_text(encoding="utf-8").lower()
    assert "alter table prompt_registry" in sql
    assert "is_active" in sql
    assert "if not exists" in sql


# ════════════════════════════════════════════════════════════════════
# upsert_seed
# ════════════════════════════════════════════════════════════════════

class TestUpsertSeed:
    def test_skips_when_content_hash_matches(self):
        from scripts.migrate_system_prompts import upsert_seed, _hash_content
        db = MagicMock()
        db.fetch_one.return_value = {"prompt_id": "p-1", "version": 3}
        out = upsert_seed(db, name="system.default", content="hello", purpose="x")
        assert out["created"] is False
        assert out["prompt_id"] == "p-1"
        # No INSERT happened; only the dedup SELECT
        sqls = [str(c.args[0]).lower() for c in db.fetch_one.call_args_list if c.args]
        assert all("insert into prompt_registry" not in s for s in sqls)

    def test_inserts_new_version_on_content_change(self):
        from scripts.migrate_system_prompts import upsert_seed
        db = MagicMock()
        # First fetch_one (dedup) → None; second (next version) →
        # {"v": 4}; third (INSERT RETURNING) → row.
        db.fetch_one.side_effect = [
            None,
            {"v": 4},
            {"prompt_id": "p-2", "version": 4},
        ]
        out = upsert_seed(db, name="system.default", content="updated", purpose="x")
        assert out["created"] is True
        assert out["version"] == 4
        sqls = [str(c.args[0]).lower() for c in db.fetch_one.call_args_list if c.args]
        assert any("insert into prompt_registry" in s for s in sqls)


class TestSeedAll:
    def test_iterates_all_system_prompts(self):
        from scripts.migrate_system_prompts import seed_all
        from services.llm import SYSTEM_PROMPTS

        db = MagicMock()
        # Always return None on dedup → every prompt counted as created.
        side_effects: list = []
        for i in range(len(SYSTEM_PROMPTS)):
            side_effects.extend([None, {"v": 1}, {"prompt_id": f"p-{i}", "version": 1}])
        db.fetch_one.side_effect = side_effects
        out = seed_all(db)
        assert out["created"] >= 1
        assert len(out["rows"]) <= len(SYSTEM_PROMPTS)


# ════════════════════════════════════════════════════════════════════
# _get_system_prompt registry-aware loader
# ════════════════════════════════════════════════════════════════════

class TestRegistryAwareLoader:
    def test_falls_back_to_dict_when_registry_unavailable(self):
        from services.llm import _get_system_prompt, SYSTEM_PROMPTS
        with patch("services.llm._load_active_prompt_from_registry", return_value=None):
            out = _get_system_prompt("compare")
        assert SYSTEM_PROMPTS["compare"][:60] in out

    def test_uses_registry_when_active_row_present(self):
        from services.llm import _get_system_prompt
        sentinel = "REGISTRY-OVERRIDE-MARKER-12345"
        with patch("services.llm._load_active_prompt_from_registry", return_value=sentinel):
            out = _get_system_prompt("compare")
        assert sentinel in out

    def test_format_hint_table_routes_to_tabular(self):
        from services.llm import _get_system_prompt
        sentinel = "TABULAR-FROM-REGISTRY"
        # Loader gets called with the tabular name when format_hint='table'.
        seen_names: list[str] = []
        def loader(name):
            seen_names.append(name)
            return sentinel
        with patch("services.llm._load_active_prompt_from_registry", side_effect=loader):
            out = _get_system_prompt("compare", format_hint="table")
        assert sentinel in out
        assert "system.tabular" in seen_names
