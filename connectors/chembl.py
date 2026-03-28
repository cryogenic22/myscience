"""ChEMBL connector — molecular bioactivity and drug target data.

Fetches drug-target interactions, bioactivity measurements, mechanism
of action details, and molecular properties from the EBI ChEMBL database.

This is the foundation of the molecular intelligence layer — enables
target-based competitive analysis, binding affinity comparison, and
drug-target selectivity profiling.

API: https://www.ebi.ac.uk/chembl/api/data/
Docs: https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services
"""

from __future__ import annotations

import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from connectors.base import (
    BaseConnector,
    HealthCheckResult,
    RawRecord,
    Provenance,
    RecordType,
    SourceType,
)

logger = logging.getLogger(__name__)

CHEMBL_API_BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLConnector(BaseConnector):
    """Connector for EBI ChEMBL bioactivity database.

    Fetches:
    - Drug molecules and their ChEMBL IDs
    - Target proteins and their classifications
    - Drug-target activity measurements (IC50, Ki, Kd, EC50)
    - Mechanism of action annotations
    - Drug indications from ChEMBL
    """

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._target_drugs = (target_overrides or {}).get("drugs", [])
        self._max_per_drug = (target_overrides or {}).get("max_activities", 50)

    def source_type(self) -> SourceType:
        return SourceType.CHEMBL

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.get(f"{CHEMBL_API_BASE}/status.json", timeout=10)
            return HealthCheckResult(
                source_type=self.source_type,
                healthy=resp.status_code == 200,
                response_time_ms=0,
                message=f"ChEMBL API: HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type,
                healthy=False,
                response_time_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch molecular data for target drugs."""
        records: list[RawRecord] = []
        drugs = self._target_drugs or self._get_target_drugs()

        for drug_name in drugs[:30]:
            try:
                # 1. Search for molecule by name
                mol = self._search_molecule(drug_name)
                if not mol:
                    continue

                chembl_id = mol.get("molecule_chembl_id", "")
                records.append(self._molecule_record(mol, drug_name))

                # 2. Fetch mechanism of action
                moa_records = self._fetch_mechanisms(chembl_id, drug_name)
                records.extend(moa_records)

                # 3. Fetch top bioactivities (target interactions)
                activity_records = self._fetch_activities(chembl_id, drug_name)
                records.extend(activity_records)

            except Exception as e:
                logger.warning("ChEMBL fetch failed for %s: %s", drug_name, e)

        logger.info("ChEMBL connector fetched %d records", len(records))
        return records

    def _search_molecule(self, drug_name: str) -> Optional[dict]:
        """Search ChEMBL for a molecule by name."""
        try:
            resp = self._fetch_with_retry(
                f"{CHEMBL_API_BASE}/molecule/search.json",
                params={"q": drug_name, "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                molecules = data.get("molecules", [])
                if molecules:
                    return molecules[0]
        except Exception as e:
            logger.debug("ChEMBL molecule search failed for %s: %s", drug_name, e)
        return None

    def _molecule_record(self, mol: dict, drug_name: str) -> RawRecord:
        """Convert ChEMBL molecule to RawRecord."""
        chembl_id = mol.get("molecule_chembl_id", "")
        props = mol.get("molecule_properties", {}) or {}

        return RawRecord(
            record_type=RecordType.DRUG,
            external_id=chembl_id,
            source_name="ChEMBL",
            provenance=Provenance(
                source_type=self.source_type,
                api_endpoint=f"{CHEMBL_API_BASE}/molecule/search.json",
                query_params={"q": drug_name},
                retrieved_at=datetime.now(timezone.utc),
                raw_response_hash=self._hash(mol),
            ),
            data={
                "generic_name": drug_name,
                "chembl_id": chembl_id,
                "molecule_type": mol.get("molecule_type", ""),
                "max_phase": mol.get("max_phase", 0),
                "first_approval": mol.get("first_approval"),
                "oral": mol.get("oral", False),
                "parenteral": mol.get("parenteral", False),
                "topical": mol.get("topical", False),
                "molecular_weight": props.get("full_mwt"),
                "alogp": props.get("alogp"),
                "hba": props.get("hba"),
                "hbd": props.get("hbd"),
                "psa": props.get("psa"),
                "num_ro5_violations": props.get("num_ro5_violations"),
                "molecular_formula": props.get("full_molformula"),
                "smiles": mol.get("molecule_structures", {}).get("canonical_smiles") if mol.get("molecule_structures") else None,
            },
            identifiers={
                "chembl_id": chembl_id,
                "generic_name": drug_name,
            },
        )

    def _fetch_mechanisms(self, chembl_id: str, drug_name: str) -> list[RawRecord]:
        """Fetch mechanism of action for a molecule."""
        records = []
        try:
            resp = self._fetch_with_retry(
                f"{CHEMBL_API_BASE}/mechanism.json",
                params={"molecule_chembl_id": chembl_id, "limit": 10},
            )
            if resp.status_code != 200:
                return records

            data = resp.json()
            for mech in data.get("mechanisms", []):
                target_name = mech.get("target_chembl_id", "")
                records.append(RawRecord(
                    record_type=RecordType.ONTOLOGY_TERM,
                    external_id=f"{chembl_id}_moa_{target_name}",
                    source_name="ChEMBL",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=f"{CHEMBL_API_BASE}/mechanism.json",
                        query_params={"molecule_chembl_id": chembl_id},
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=self._hash(mech),
                    ),
                    data={
                        "drug_name": drug_name,
                        "chembl_id": chembl_id,
                        "mechanism_of_action": mech.get("mechanism_of_action", ""),
                        "action_type": mech.get("action_type", ""),
                        "target_chembl_id": target_name,
                        "target_name": mech.get("target_name", ""),
                        "target_type": mech.get("target_type", ""),
                        "binding_site_name": mech.get("binding_site_name"),
                        "selectivity_comment": mech.get("selectivity_comment"),
                    },
                    identifiers={
                        "chembl_id": chembl_id,
                        "target_chembl_id": target_name,
                    },
                ))
        except Exception as e:
            logger.debug("ChEMBL mechanism fetch failed for %s: %s", chembl_id, e)
        return records

    def _fetch_activities(self, chembl_id: str, drug_name: str) -> list[RawRecord]:
        """Fetch top bioactivity measurements (IC50, Ki, etc.)."""
        records = []
        try:
            resp = self._fetch_with_retry(
                f"{CHEMBL_API_BASE}/activity.json",
                params={
                    "molecule_chembl_id": chembl_id,
                    "limit": self._max_per_drug,
                    "order_by": "-pchembl_value",  # most potent first
                },
            )
            if resp.status_code != 200:
                return records

            data = resp.json()
            for act in data.get("activities", []):
                activity_id = act.get("activity_id", "")
                records.append(RawRecord(
                    record_type=RecordType.ONTOLOGY_TERM,
                    external_id=f"chembl_activity_{activity_id}",
                    source_name="ChEMBL",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=f"{CHEMBL_API_BASE}/activity.json",
                        query_params={"molecule_chembl_id": chembl_id},
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=self._hash(act),
                    ),
                    data={
                        "drug_name": drug_name,
                        "chembl_id": chembl_id,
                        "target_chembl_id": act.get("target_chembl_id", ""),
                        "target_name": act.get("target_pref_name", ""),
                        "target_organism": act.get("target_organism", ""),
                        "activity_type": act.get("standard_type", ""),  # IC50, Ki, EC50
                        "activity_value": act.get("standard_value"),
                        "activity_units": act.get("standard_units", ""),
                        "activity_relation": act.get("standard_relation", "="),
                        "pchembl_value": act.get("pchembl_value"),  # -log10(molar), higher = more potent
                        "assay_type": act.get("assay_type", ""),
                        "assay_description": act.get("assay_description", ""),
                    },
                    identifiers={
                        "chembl_id": chembl_id,
                        "activity_id": str(activity_id),
                    },
                ))
        except Exception as e:
            logger.debug("ChEMBL activity fetch failed for %s: %s", chembl_id, e)
        return records

    def _get_target_drugs(self) -> list[str]:
        """Get target drug names from config or defaults."""
        try:
            from config import config
            names = list(getattr(config.pipeline, 'target_drug_names', []))
            if names:
                return names[:30]
        except Exception:
            pass
        return [
            "semaglutide", "tirzepatide", "empagliflozin", "dapagliflozin",
            "liraglutide", "sitagliptin", "canagliflozin", "dulaglutide",
            "metformin", "pioglitazone", "valsartan", "atorvastatin",
        ]

    @staticmethod
    def _hash(data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
