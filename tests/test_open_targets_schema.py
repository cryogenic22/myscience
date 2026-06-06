"""Open Targets connector — GraphQL schema-drift regression (no network).

The v4 API retired `Drug.linkedTargets` (and `maximumClinicalTrialPhase`) in
favour of `mechanismsOfAction.rows[].targets[]`. The old traversal silently
fetched 0 targets while logging SUCCESS — the exact silent-zero failure mode
this sweep hunts. These tests pin the tolerant extraction so a future shape
change is caught instead of going quiet.
"""

from __future__ import annotations

from connectors.open_targets import OpenTargetsConnector


def test_extract_targets_current_v4_shape():
    """mechanismsOfAction.rows[].targets[] is the live (2026) shape."""
    drug_data = {
        "id": "CHEMBL1431",
        "mechanismsOfAction": {
            "rows": [
                {
                    "mechanismOfAction": "Complex I inhibitor",
                    "targets": [
                        {"id": "ENSG00000198695", "approvedSymbol": "MT-ND6"},
                        {"id": "ENSG00000130414", "approvedSymbol": "NDUFA10"},
                    ],
                }
            ]
        },
    }
    targets = OpenTargetsConnector._extract_targets(drug_data)
    assert {t["id"] for t in targets} == {"ENSG00000198695", "ENSG00000130414"}
    assert {t["approvedSymbol"] for t in targets} == {"MT-ND6", "NDUFA10"}


def test_extract_targets_legacy_shape_still_supported():
    """The retired linkedTargets shape is tolerated as a fallback."""
    drug_data = {
        "id": "CHEMBL25",
        "linkedTargets": {"rows": [{"id": "ENSG00000073756", "approvedSymbol": "PTGS2"}]},
    }
    targets = OpenTargetsConnector._extract_targets(drug_data)
    assert targets == [{"id": "ENSG00000073756", "approvedSymbol": "PTGS2"}]


def test_extract_targets_dedupes_across_mechanisms():
    """A target appearing in two mechanisms is emitted once."""
    drug_data = {
        "mechanismsOfAction": {
            "rows": [
                {"targets": [{"id": "ENSG1", "approvedSymbol": "A"}]},
                {"targets": [{"id": "ENSG1", "approvedSymbol": "A"}, {"id": "ENSG2", "approvedSymbol": "B"}]},
            ]
        }
    }
    targets = OpenTargetsConnector._extract_targets(drug_data)
    assert sorted(t["id"] for t in targets) == ["ENSG1", "ENSG2"]


def test_extract_targets_empty_and_malformed_are_safe():
    assert OpenTargetsConnector._extract_targets({}) == []
    assert OpenTargetsConnector._extract_targets({"mechanismsOfAction": None}) == []
    assert OpenTargetsConnector._extract_targets({"mechanismsOfAction": {"rows": None}}) == []
    assert OpenTargetsConnector._extract_targets(
        {"mechanismsOfAction": {"rows": [{"targets": None}]}}
    ) == []
