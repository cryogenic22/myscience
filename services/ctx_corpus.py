"""PharmaCorpusBuilder — Export market_zero entities to CTX knowledge corpus.

Converts DB entities (drugs, companies, trials, mechanisms) into a structured
corpus directory, then runs the CTX packer to produce L2 + L3 documents.

Usage:
    builder = PharmaCorpusBuilder(db)
    result = builder.pack("/path/to/output")
    # result.document → L2 CTXDocument
    # result.l3_document → L3 directory index
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add ctxpack to path if not installed




try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from ctxpack.core.packer import pack as ctx_pack, PackResult


# ── SQL queries for entity export ──

_DRUGS_SQL = """
SELECT
    d.id,
    d.generic_name,
    d.brand_name,
    m.mechanism_name,
    c.company_name,
    ta.therapeutic_area,
    d.approval_status,
    d.nda_number,
    d.supply_status
FROM drugs d
LEFT JOIN mechanisms m ON d.mechanism_id = m.id
LEFT JOIN companies c ON d.company_id = c.id
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
ORDER BY d.generic_name
"""

_COMPANIES_SQL = """
SELECT
    c.id,
    c.company_name,
    COUNT(DISTINCT d.id) AS drug_count,
    COUNT(DISTINCT ct.nct_id) AS trial_count,
    COALESCE(SUM(mv.pipeline_score), 0) AS pipeline_score_total
FROM companies c
LEFT JOIN drugs d ON d.company_id = c.id
LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
LEFT JOIN mv_drug_pipeline_strength mv ON mv.drug_id = d.id
GROUP BY c.id, c.company_name
ORDER BY pipeline_score_total DESC
"""

_TRIALS_SQL = """
SELECT
    ct.nct_id,
    ct.title,
    ct.phase,
    ct.status,
    d.generic_name AS drug_name,
    ct.enrollment,
    ct.start_date
FROM clinical_trials ct
LEFT JOIN drugs d ON ct.drug_id = d.id
ORDER BY ct.start_date DESC
LIMIT 500
"""

_MECHANISMS_SQL = """
SELECT
    m.id,
    m.mechanism_name,
    COUNT(DISTINCT d.id) AS drug_count,
    COUNT(DISTINCT ct.nct_id) AS trial_count
FROM mechanisms m
LEFT JOIN drugs d ON d.mechanism_id = m.id
LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
GROUP BY m.id, m.mechanism_name
ORDER BY drug_count DESC
"""


class PharmaCorpusBuilder:
    """Export market_zero entities to CTX-packable corpus."""

    def __init__(self, db: Any):
        self.db = db

    def export_drugs(self, limit: int | None = None) -> list[dict]:
        """Export drugs with mechanism, company, therapeutic area."""
        rows = self.db.fetch_all(_DRUGS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("generic_name", "Unknown"),
                "brand_name": r.get("brand_name", ""),
                "mechanism": r.get("mechanism_name", ""),
                "company": r.get("company_name", ""),
                "therapeutic_area": r.get("therapeutic_area", ""),
                "approval_status": r.get("approval_status", ""),
                "nda_number": r.get("nda_number", ""),
                "supply_status": r.get("supply_status", ""),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def export_companies(self, limit: int | None = None) -> list[dict]:
        """Export companies with portfolio metrics."""
        rows = self.db.fetch_all(_COMPANIES_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("company_name", "Unknown"),
                "drug_count": r.get("drug_count", 0),
                "trial_count": r.get("trial_count", 0),
                "pipeline_score": r.get("pipeline_score_total", 0),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def export_trials(self, limit: int | None = None) -> list[dict]:
        """Export clinical trials with key metadata."""
        rows = self.db.fetch_all(_TRIALS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "nct_id": r.get("nct_id", ""),
                "title": r.get("title", ""),
                "phase": r.get("phase", ""),
                "status": r.get("status", ""),
                "drug_name": r.get("drug_name", ""),
                "enrollment": r.get("enrollment", 0),
                "start_date": str(r.get("start_date", "")),
            }
            for r in rows
        ]

    def export_mechanisms(self, limit: int | None = None) -> list[dict]:
        """Export mechanisms with drug/trial counts."""
        rows = self.db.fetch_all(_MECHANISMS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("mechanism_name", "Unknown"),
                "drug_count": r.get("drug_count", 0),
                "trial_count": r.get("trial_count", 0),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def build_corpus_dir(self, output_dir: str) -> str:
        """Write entity YAML files to corpus directory.

        Creates:
            output_dir/drugs.yaml
            output_dir/companies.yaml
            output_dir/trials.yaml
            output_dir/mechanisms.yaml
            output_dir/ctxpack.yaml  (packer config)
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        drugs = self.export_drugs()
        companies = self.export_companies()
        trials = self.export_trials()
        mechanisms = self.export_mechanisms()

        # Write entity files — one YAML file per entity for CTX packer
        # Each file uses {"entity": name, ...fields} format
        for drug in drugs:
            name = drug["name"]
            safe_name = name.lower().replace(" ", "_").replace("/", "_")[:50]
            self._write_yaml(out / f"drug_{safe_name}.yaml", {
                "entity": f"DRUG-{name.upper().replace(' ', '-')}",
                "type": "drug",
                "identifier": drug.get("id", ""),
                **{k: v for k, v in drug.items() if k != "id" and v},
            })

        for company in companies:
            name = company["name"]
            safe_name = name.lower().replace(" ", "_").replace("/", "_")[:50]
            self._write_yaml(out / f"company_{safe_name}.yaml", {
                "entity": f"COMPANY-{name.upper().replace(' ', '-')}",
                "type": "company",
                "identifier": company.get("id", ""),
                **{k: v for k, v in company.items() if k != "id" and v},
            })

        for mech in mechanisms:
            name = mech["name"]
            safe_name = name.lower().replace(" ", "_").replace("/", "_")[:50]
            self._write_yaml(out / f"mechanism_{safe_name}.yaml", {
                "entity": f"MECHANISM-{name.upper().replace(' ', '-')[:60]}",
                "type": "mechanism",
                "identifier": mech.get("id", ""),
                **{k: v for k, v in mech.items() if k != "id" and v},
            })

        # Trials: group top trials as a list within a single entity file
        # (too many for individual files)
        if trials:
            trial_entries = {}
            for trial in trials[:200]:  # cap at 200
                nct = trial.get("nct_id", "unknown")
                trial_entries[nct] = {
                    "title": trial.get("title", ""),
                    "phase": trial.get("phase", ""),
                    "status": trial.get("status", ""),
                    "drug": trial.get("drug_name", ""),
                    "enrollment": trial.get("enrollment", 0),
                }
            self._write_yaml(out / "trials.yaml", trial_entries)

        # Write packer config
        config = {
            "domain": "pharma-intelligence",
            "scope": "market-zero-knowledge-base",
            "author": "market-zero-pipeline",
            "layers": ["L2", "L3"],
            "preset": "balanced",
            "provenance": "inline",
        }
        self._write_yaml(out / "ctxpack.yaml", config)

        logger.info(
            "Corpus built: %d drugs, %d companies, %d trials, %d mechanisms → %s",
            len(drugs), len(companies), len(trials), len(mechanisms), output_dir,
        )
        return output_dir

    def pack(self, output_dir: str) -> PackResult:
        """Build corpus directory and run CTX packer → L2 + L3 documents."""
        self.build_corpus_dir(output_dir)
        result = ctx_pack(
            output_dir,
            domain="pharma-intelligence",
            scope="market-zero-knowledge-base",
            author="market-zero-pipeline",
            layers=["L2", "L3"],
            preset="balanced",
        )
        logger.info(
            "Packed: %d entities, %d source tokens, %d warnings",
            result.entity_count,
            result.source_token_count,
            result.warning_count,
        )
        return result

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> None:
        """Write data to YAML file."""
        if yaml is not None:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        else:
            # Fallback: write as JSON (CTX packer can read JSON too)
            json_path = path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
