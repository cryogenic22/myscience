"""PubChem connector — chemical identity, properties, and bioassays.

Fetches compound identifiers (CID, InChI, SMILES), molecular properties,
synonyms, and bioassay results from NCBI PubChem.

This provides the molecular identity layer — connecting drug names to
chemical structures, enabling structure-based search and similarity analysis.

API: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
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

PUBCHEM_API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class PubChemConnector(BaseConnector):
    """Connector for NCBI PubChem compound data.

    Fetches:
    - Compound identity (CID, canonical SMILES, InChI, molecular formula)
    - Molecular properties (MW, LogP, H-bond donors/acceptors, TPSA)
    - Synonyms and name mappings
    - Pharmacological classification
    """

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._target_drugs = (target_overrides or {}).get("drugs", [])

    @property
    def source_type(self) -> SourceType:
        return SourceType.PUBCHEM

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.get(
                f"{PUBCHEM_API_BASE}/compound/name/aspirin/property/MolecularFormula/JSON",
                timeout=10,
            )
            return HealthCheckResult(
                source_type=self.source_type,
                available=resp.status_code == 200,
                latency_ms=0,
                message=f"PubChem API: HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type,
                available=False,
                latency_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch molecular data for target drugs from PubChem."""
        records: list[RawRecord] = []
        drugs = self._target_drugs or self._get_target_drugs()

        for drug_name in drugs[:30]:
            try:
                # 1. Get compound properties
                compound = self._fetch_compound(drug_name)
                if compound:
                    records.append(compound)

                # 2. Get synonyms
                synonyms = self._fetch_synonyms(drug_name)
                if synonyms:
                    records.append(synonyms)

            except Exception as e:
                logger.warning("PubChem fetch failed for %s: %s", drug_name, e)

            # Rate limit: PubChem allows 5 requests/second
            import time
            time.sleep(0.25)

        logger.info("PubChem connector fetched %d records", len(records))
        return records

    def _fetch_compound(self, drug_name: str) -> Optional[RawRecord]:
        """Fetch compound properties from PubChem."""
        properties = [
            "MolecularFormula", "MolecularWeight", "CanonicalSMILES",
            "InChI", "InChIKey", "XLogP", "HBondDonorCount",
            "HBondAcceptorCount", "TPSA", "RotatableBondCount",
            "Complexity", "IUPACName", "CID",
        ]

        try:
            resp = self._fetch_with_retry(
                f"{PUBCHEM_API_BASE}/compound/name/{drug_name}/property/{','.join(properties)}/JSON",
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            props_list = data.get("PropertyTable", {}).get("Properties", [])
            if not props_list:
                return None

            props = props_list[0]
            cid = str(props.get("CID", ""))

            return RawRecord(
                record_type=RecordType.DRUG,
                external_id=f"pubchem_{cid}",
                source_name="PubChem",
                provenance=Provenance(
                    source_type=self.source_type,
                    api_endpoint=f"{PUBCHEM_API_BASE}/compound/name/{drug_name}/property/",
                    query_params={"properties": properties},
                    retrieved_at=datetime.now(timezone.utc),
                    raw_response_hash=self._hash(props),
                ),
                data={
                    "generic_name": drug_name,
                    "pubchem_cid": cid,
                    "molecular_formula": props.get("MolecularFormula"),
                    "molecular_weight": props.get("MolecularWeight"),
                    "canonical_smiles": props.get("CanonicalSMILES"),
                    "inchi": props.get("InChI"),
                    "inchi_key": props.get("InChIKey"),
                    "xlogp": props.get("XLogP"),
                    "hbd": props.get("HBondDonorCount"),
                    "hba": props.get("HBondAcceptorCount"),
                    "tpsa": props.get("TPSA"),
                    "rotatable_bonds": props.get("RotatableBondCount"),
                    "complexity": props.get("Complexity"),
                    "iupac_name": props.get("IUPACName"),
                },
                identifiers={
                    "pubchem_cid": cid,
                    "generic_name": drug_name,
                },
            )
        except Exception as e:
            logger.debug("PubChem compound fetch failed for %s: %s", drug_name, e)
        return None

    def _fetch_synonyms(self, drug_name: str) -> Optional[RawRecord]:
        """Fetch compound synonyms from PubChem."""
        try:
            resp = self._fetch_with_retry(
                f"{PUBCHEM_API_BASE}/compound/name/{drug_name}/synonyms/JSON",
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            info_list = data.get("InformationList", {}).get("Information", [])
            if not info_list:
                return None

            info = info_list[0]
            cid = str(info.get("CID", ""))
            synonyms = info.get("Synonym", [])[:50]  # cap

            return RawRecord(
                record_type=RecordType.DRUG,
                external_id=f"pubchem_syn_{cid}",
                source_name="PubChem",
                provenance=Provenance(
                    source_type=self.source_type,
                    api_endpoint=f"{PUBCHEM_API_BASE}/compound/name/{drug_name}/synonyms/",
                    query_params={},
                    retrieved_at=datetime.now(timezone.utc),
                    raw_response_hash=self._hash({"synonyms": synonyms[:10]}),
                ),
                data={
                    "generic_name": drug_name,
                    "pubchem_cid": cid,
                    "synonyms": synonyms,
                    "synonym_count": len(synonyms),
                },
                identifiers={
                    "pubchem_cid": cid,
                    "generic_name": drug_name,
                },
            )
        except Exception as e:
            logger.debug("PubChem synonyms failed for %s: %s", drug_name, e)
        return None

    def _get_target_drugs(self) -> list[str]:
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
