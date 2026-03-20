"""Tests for domain/ta_definitions/schema.py — TA definition loading.

TDD: Verify YAML loading, dataclass construction, and connector overrides.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class TestTADefinition:
    """Verify TADefinition dataclass behavior."""

    def test_auto_display_name(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(name="oncology")
        assert ta.display_name == "Oncology"

    def test_custom_display_name(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(name="oncology", display_name="Solid Tumors")
        assert ta.display_name == "Solid Tumors"

    def test_shortage_defaults_to_drugs(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(name="test", target_drugs=["drug_a", "drug_b"])
        assert ta.shortage_search_terms == ["drug_a", "drug_b"]

    def test_custom_shortage_terms(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(
            name="test",
            target_drugs=["drug_a"],
            shortage_search_terms=["custom_term"],
        )
        assert ta.shortage_search_terms == ["custom_term"]

    def test_target_ciks_extracts_from_companies(self):
        from domain.ta_definitions.schema import TADefinition, CompanyTarget
        ta = TADefinition(
            name="test",
            target_companies=[
                CompanyTarget(name="Merck", cik="0000310158"),
                CompanyTarget(name="Roche"),  # no CIK
            ],
        )
        assert ta.target_ciks == ["0000310158"]


class TestConnectorOverrides:
    """Verify to_connector_overrides() produces correct override dicts."""

    def test_all_connectors_present(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(name="test", target_drugs=["pembrolizumab"])
        overrides = ta.to_connector_overrides()

        expected_keys = {"mesh", "orange_book", "clinical_trials", "pubmed",
                         "openfda_faers", "openfda_labels", "fda_shortages", "sec_edgar"}
        assert set(overrides.keys()) == expected_keys

    def test_clinical_trials_overrides(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(
            name="test",
            target_drugs=["pembrolizumab", "nivolumab"],
            target_conditions=["lung cancer"],
        )
        ct = ta.to_connector_overrides()["clinical_trials"]
        assert ct["drugs"] == ["pembrolizumab", "nivolumab"]
        assert ct["conditions"] == ["lung cancer"]

    def test_mesh_overrides(self):
        from domain.ta_definitions.schema import TADefinition
        ta = TADefinition(
            name="test",
            mesh_ids=["D009369"],
            mechanism_mesh_ids=["D000074322"],
        )
        mesh = ta.to_connector_overrides()["mesh"]
        assert mesh["mesh_ids"] == ["D009369"]
        assert mesh["mechanism_ids"] == ["D000074322"]


class TestLoadTADefinition:
    """Verify YAML loading."""

    def test_loads_oncology_yaml(self):
        from domain.ta_definitions.schema import load_ta_definition
        ta = load_ta_definition("domain/ta_definitions/oncology.yaml")
        assert ta.name == "oncology"
        assert ta.display_name == "Oncology"
        assert len(ta.target_drugs) >= 30
        assert len(ta.target_conditions) >= 10
        assert len(ta.mesh_ids) >= 10
        assert len(ta.target_companies) >= 5

    def test_loads_from_minimal_yaml(self):
        yaml_content = """
name: test_ta
target_drugs:
  - drug_x
target_conditions:
  - condition_y
"""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        from domain.ta_definitions.schema import load_ta_definition
        ta = load_ta_definition(path)
        assert ta.name == "test_ta"
        assert ta.target_drugs == ["drug_x"]
        assert ta.target_conditions == ["condition_y"]
        assert ta.display_name == "Test Ta"

        Path(path).unlink()

    def test_raises_on_missing_file(self):
        from domain.ta_definitions.schema import load_ta_definition
        with pytest.raises(FileNotFoundError):
            load_ta_definition("nonexistent.yaml")

    def test_company_targets_parsed(self):
        from domain.ta_definitions.schema import load_ta_definition
        ta = load_ta_definition("domain/ta_definitions/oncology.yaml")
        merck = [c for c in ta.target_companies if c.name == "Merck"]
        assert len(merck) == 1
        assert merck[0].cik == "0000310158"
        assert merck[0].ticker == "MRK"
