"""TA definition schema for automated onboarding.

Phase 3.1: Defines the TADefinition dataclass and YAML loader.

Each TA definition file specifies everything needed to onboard a new
therapeutic area: MeSH IDs, seed drugs, conditions, companies, and
PubMed queries.

Usage:
    from domain.ta_definitions.schema import TADefinition, load_ta_definition
    ta = load_ta_definition("domain/ta_definitions/oncology.yaml")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CompanyTarget:
    """A target company for SEC EDGAR and entity enrichment."""
    name: str
    cik: str = ""
    ticker: str = ""
    country: str = ""


@dataclass
class TADefinition:
    """Complete definition for onboarding a therapeutic area."""

    # Identity
    name: str                                      # e.g., "oncology"
    display_name: str = ""                         # e.g., "Oncology"

    # MeSH ontology
    mesh_ids: list[str] = field(default_factory=list)           # TA MeSH descriptors
    mechanism_mesh_ids: list[str] = field(default_factory=list) # Mechanism MeSH descriptors

    # Drug targets
    target_drugs: list[str] = field(default_factory=list)       # Seed drug generic names

    # Clinical trials targets
    target_conditions: list[str] = field(default_factory=list)  # CT.gov condition terms

    # Orange Book EPC classes
    target_epc_classes: list[str] = field(default_factory=list)

    # Company targets
    target_companies: list[CompanyTarget] = field(default_factory=list)

    # PubMed search queries
    pubmed_queries: list[str] = field(default_factory=list)

    # FDA shortage search terms (defaults to target_drugs if empty)
    shortage_search_terms: list[str] = field(default_factory=list)

    # TA condition keyword mappings for backfill_ta_links
    condition_keywords: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.replace("_", " ").title()
        if not self.shortage_search_terms:
            self.shortage_search_terms = list(self.target_drugs)

    @property
    def target_ciks(self) -> list[str]:
        """Extract CIK list for SEC EDGAR connector."""
        return [c.cik for c in self.target_companies if c.cik]

    def to_connector_overrides(self) -> dict[str, dict[str, Any]]:
        """Generate per-connector target override dicts."""
        return {
            "mesh": {
                "mesh_ids": self.mesh_ids,
                "mechanism_ids": self.mechanism_mesh_ids,
            },
            "orange_book": {
                "epc_classes": self.target_epc_classes,
            },
            "clinical_trials": {
                "drugs": self.target_drugs,
                "conditions": self.target_conditions,
            },
            "pubmed": {
                "queries": self.pubmed_queries,
            },
            "openfda_faers": {
                "drugs": self.target_drugs,
            },
            "openfda_labels": {
                "drugs": self.target_drugs,
            },
            "fda_shortages": {
                "search_terms": self.shortage_search_terms,
            },
            "sec_edgar": {
                "ciks": self.target_ciks,
            },
        }


def load_ta_definition(path: str | Path) -> TADefinition:
    """Load a TADefinition from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"TA definition not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    # Parse company targets
    companies = []
    for c in data.get("target_companies", []):
        if isinstance(c, dict):
            companies.append(CompanyTarget(**c))
        elif isinstance(c, str):
            companies.append(CompanyTarget(name=c))

    return TADefinition(
        name=data["name"],
        display_name=data.get("display_name", ""),
        mesh_ids=data.get("mesh_ids", []),
        mechanism_mesh_ids=data.get("mechanism_mesh_ids", []),
        target_drugs=data.get("target_drugs", []),
        target_conditions=data.get("target_conditions", []),
        target_epc_classes=data.get("target_epc_classes", []),
        target_companies=companies,
        pubmed_queries=data.get("pubmed_queries", []),
        shortage_search_terms=data.get("shortage_search_terms", []),
        condition_keywords=data.get("condition_keywords", {}),
    )
