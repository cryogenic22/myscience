"""Tests for connector target_overrides — Phase 3.3.

TDD: Verify each connector respects target_overrides and falls back to defaults.
"""

from __future__ import annotations

import pytest


class TestClinicalTrialsOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.clinical_trials import ClinicalTrialsConnector, TARGET_DRUG_NAMES, TARGET_CONDITIONS
        c = ClinicalTrialsConnector()
        assert c._drugs is TARGET_DRUG_NAMES
        assert c._conditions is TARGET_CONDITIONS

    def test_overrides_drugs(self):
        from connectors.clinical_trials import ClinicalTrialsConnector
        custom = ["pembrolizumab", "nivolumab"]
        c = ClinicalTrialsConnector(target_overrides={"drugs": custom})
        assert c._drugs == custom

    def test_overrides_conditions(self):
        from connectors.clinical_trials import ClinicalTrialsConnector
        custom = ["lung cancer"]
        c = ClinicalTrialsConnector(target_overrides={"conditions": custom})
        assert c._conditions == custom

    def test_partial_override(self):
        from connectors.clinical_trials import ClinicalTrialsConnector, TARGET_CONDITIONS
        c = ClinicalTrialsConnector(target_overrides={"drugs": ["drug_x"]})
        assert c._drugs == ["drug_x"]
        assert c._conditions is TARGET_CONDITIONS


class TestPubMedOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.pubmed import PubMedConnector, TARGET_SEARCH_QUERIES
        c = PubMedConnector()
        assert c._queries is TARGET_SEARCH_QUERIES

    def test_overrides_queries(self):
        from connectors.pubmed import PubMedConnector
        custom = ['"checkpoint inhibitor"[Title]']
        c = PubMedConnector(target_overrides={"queries": custom})
        assert c._queries == custom


class TestFAERSOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.openfda_faers import OpenFDAFAERSConnector, TARGET_DRUGS
        c = OpenFDAFAERSConnector()
        assert c._drugs is TARGET_DRUGS

    def test_overrides_drugs(self):
        from connectors.openfda_faers import OpenFDAFAERSConnector
        custom = ["pembrolizumab"]
        c = OpenFDAFAERSConnector(target_overrides={"drugs": custom})
        assert c._drugs == custom


class TestLabelsOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.openfda_labels import OpenFDALabelsConnector, TARGET_DRUGS
        c = OpenFDALabelsConnector()
        assert c._drugs is TARGET_DRUGS

    def test_overrides_drugs(self):
        from connectors.openfda_labels import OpenFDALabelsConnector
        custom = ["atezolizumab"]
        c = OpenFDALabelsConnector(target_overrides={"drugs": custom})
        assert c._drugs == custom


class TestOrangeBookOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.orange_book import OrangeBookConnector, TARGET_PHARM_CLASSES
        c = OrangeBookConnector()
        assert c._epc_classes is TARGET_PHARM_CLASSES

    def test_overrides_epc_classes(self):
        from connectors.orange_book import OrangeBookConnector
        custom = ["Kinase Inhibitor [EPC]"]
        c = OrangeBookConnector(target_overrides={"epc_classes": custom})
        assert c._epc_classes == custom


class TestFDAShortagesOverrides:
    def test_uses_defaults_without_overrides(self):
        from connectors.fda_shortages import FDAShortagesConnector, TARGET_SEARCH_TERMS
        c = FDAShortagesConnector()
        assert c._search_terms is TARGET_SEARCH_TERMS

    def test_overrides_search_terms(self):
        from connectors.fda_shortages import FDAShortagesConnector
        custom = ["nivolumab"]
        c = FDAShortagesConnector(target_overrides={"search_terms": custom})
        assert c._search_terms == custom


class TestSECEdgarOverrides:
    def test_uses_config_ciks_without_overrides(self):
        from connectors.sec_edgar import SECEdgarConnector
        c = SECEdgarConnector()
        # Without config, defaults to empty
        assert c.target_ciks == []

    def test_overrides_ciks(self):
        from connectors.sec_edgar import SECEdgarConnector
        custom = ["0000310158"]
        c = SECEdgarConnector(target_overrides={"ciks": custom})
        assert c.target_ciks == custom


class TestMeSHOverrides:
    def test_uses_config_defaults_without_overrides(self):
        from connectors.mesh import MeSHConnector
        c = MeSHConnector()
        # Should use config.target_mesh_ids
        from config import config
        assert c._mesh_ids == config.target_mesh_ids

    def test_overrides_mesh_ids(self):
        from connectors.mesh import MeSHConnector
        custom = ["D009369"]
        c = MeSHConnector(target_overrides={"mesh_ids": custom})
        assert c._mesh_ids == custom

    def test_overrides_mechanism_ids(self):
        from connectors.mesh import MeSHConnector
        custom = ["D000074322"]
        c = MeSHConnector(target_overrides={"mechanism_ids": custom})
        assert c._mechanism_ids == custom
