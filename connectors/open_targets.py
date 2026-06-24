"""Open Targets Platform connector — genetic evidence for drug targets.

Fetches target-disease association scores, genetic evidence, and
druggability assessments from the Open Targets Platform (EBI/Wellcome).

This connects drugs to their biological rationale — genetic evidence
validates whether a drug target is causal in disease, which is the
strongest predictor of clinical trial success.

API: https://platform-api.opentargets.io/api/v4/graphql
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

OT_API_URL = "https://api.platform.opentargets.org/api/v4/graphql"


class OpenTargetsConnector(BaseConnector):
    """Connector for Open Targets Platform.

    Fetches:
    - Target-disease association scores (genetic, known drug, literature)
    - Druggability assessments for protein targets
    - Genetic evidence (GWAS, rare disease, somatic mutations)
    """

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._target_drugs = (target_overrides or {}).get("drugs", [])

    def source_type(self) -> SourceType:
        return SourceType.OPEN_TARGETS

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.post(
                OT_API_URL,
                json={"query": "{ meta { apiVersion { x y z } } }"},
                timeout=10,
            )
            return HealthCheckResult(
                source_type=self.source_type(),
                healthy=resp.status_code == 200,
                response_time_ms=0,
                message=f"Open Targets API: HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type(),
                healthy=False,
                response_time_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch target-disease associations for our drug targets."""
        import requests
        records: list[RawRecord] = []
        drugs = self._target_drugs or self._get_target_drugs()

        for drug_name in drugs[:20]:
            try:
                # Search for drug in Open Targets
                drug_data = self._search_drug(drug_name)
                if not drug_data:
                    continue

                drug_id = drug_data.get("id", "")
                # API v4 (2026): drug→target now lives under
                # mechanismsOfAction.rows[].targets[], not the retired
                # `linkedTargets` field. _extract_targets handles both shapes.
                targets = self._extract_targets(drug_data)

                for target in targets[:10]:
                    target_id = target.get("id", "")
                    if not target_id:
                        continue
                    target_data = self._fetch_target_associations(target_id)
                    if target_data:
                        records.extend(self._make_disease_records(drug_name, drug_id, target_data))

            except Exception as e:
                logger.warning("Open Targets fetch failed for %s: %s", drug_name, e)

        logger.info("Open Targets connector fetched %d records", len(records))
        return records

    @staticmethod
    def _extract_targets(drug_data: dict) -> list[dict]:
        """Pull the unique target rows from a drug-detail response.

        Tolerant of both the current v4 shape
        (``mechanismsOfAction.rows[].targets[]``) and the legacy
        ``linkedTargets.rows[]`` shape, so the connector keeps working across
        an API schema change instead of silently fetching zero records.
        """
        seen: dict[str, dict] = {}
        # Current shape: mechanismsOfAction → rows → targets
        for moa in (drug_data.get("mechanismsOfAction", {}) or {}).get("rows", []) or []:
            for tgt in moa.get("targets", []) or []:
                tid = tgt.get("id", "")
                if tid and tid not in seen:
                    seen[tid] = {"id": tid, "approvedSymbol": tgt.get("approvedSymbol", "")}
        # Legacy fallback
        for tgt in (drug_data.get("linkedTargets", {}) or {}).get("rows", []) or []:
            tid = tgt.get("id", "")
            if tid and tid not in seen:
                seen[tid] = {"id": tid, "approvedSymbol": tgt.get("approvedSymbol", "")}
        return list(seen.values())

    def _search_drug(self, drug_name: str) -> Optional[dict]:
        """Search Open Targets for a drug by name."""
        import requests
        # Use simple inline query (no variables) — more reliable across API versions
        query = (
            '{ search(queryString: "' + drug_name.replace('"', '') + '", '
            'entityNames: ["drug"], page: {size: 1, index: 0}) { '
            'hits { id name entity } } }'
        )
        try:
            resp = requests.post(OT_API_URL, json={"query": query}, timeout=15)
            if resp.status_code != 200:
                return None

            data = resp.json()
            if "errors" in data:
                logger.warning("Open Targets GraphQL error: %s", data["errors"][:1])
                return None
            hits = data.get("data", {}).get("search", {}).get("hits", [])
            for hit in hits:
                if hit.get("entity") == "drug":
                    # Fetch full drug details with linked targets
                    drug_id = hit.get("id", "")
                    return self._fetch_drug_details(drug_id, drug_name)
        except Exception as e:
            logger.debug("Open Targets drug search failed for %s: %s", drug_name, e)
        return None

    def _fetch_drug_details(self, drug_id: str, drug_name: str) -> Optional[dict]:
        """Fetch drug details including linked targets."""
        import requests
        query = (
            '{ drug(chemblId: "' + drug_id + '") { '
            'id name drugType maximumClinicalStage '
            'mechanismsOfAction { rows { mechanismOfAction actionType '
            'targets { id approvedSymbol } } } } }'
        )
        try:
            resp = requests.post(OT_API_URL, json={"query": query}, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "errors" in data:
                logger.warning("Open Targets drug-detail GraphQL error: %s", data["errors"][:1])
                return {"id": drug_id, "name": drug_name, "mechanismsOfAction": {"rows": []}}
            return data.get("data", {}).get("drug")
        except Exception as e:
            logger.debug("Open Targets drug details failed for %s: %s", drug_id, e)
        return None

    def _fetch_target_associations(self, target_id: str) -> Optional[dict]:
        """Fetch top disease associations for a target."""
        import requests
        query = """
        query targetAssociations($targetId: String!) {
            target(ensemblId: $targetId) {
                id
                approvedSymbol
                approvedName
                biotype
                tractability {
                    label
                    modality
                    value
                }
                associatedDiseases(page: {size: 5, index: 0}) {
                    count
                    rows {
                        disease {
                            id
                            name
                        }
                        score
                        datatypeScores {
                            id
                            score
                        }
                    }
                }
            }
        }
        """
        try:
            resp = requests.post(
                OT_API_URL,
                json={"query": query, "variables": {"targetId": target_id}},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {}).get("target")
        except Exception as e:
            logger.debug("Open Targets target fetch failed for %s: %s", target_id, e)
        return None

    def _make_disease_records(
        self, drug_name: str, drug_id: str, target: dict
    ) -> list[RawRecord]:
        """Emit one NAMED therapeutic-area ontology term per associated disease.

        Open Targets returns target-disease associations: each carries a disease
        with an EFO/MONDO id + a human name. The old code packed the whole
        association *array* into a single ONTOLOGY_TERM with no top-level `name`,
        so `_store_ontology_term` could only fail-closed (skip) or crash on the
        NOT NULL `name` constraint — the #1 active DLQ cause (3,121 records).

        Modelling each disease as its own named term lets the data actually land
        and dedupe idempotently on the stable ontology id (the disease, not the
        drug/target, is the identity — so the same disease reached via several
        drugs collapses to one therapeutic_areas row). A disease missing either
        its name or its id is skipped at the source (conservation: do not emit a
        record that can only fail downstream).

        NOTE: the association score, datatype scores, tractability and the
        target itself are intentionally NOT persisted here — `therapeutic_areas`
        has no column for them and there is no association-edge table yet. They
        remain in the source payload; capturing them is a separate, scoped loop.
        """
        records: list[RawRecord] = []
        for row in (target.get("associatedDiseases") or {}).get("rows") or []:
            disease = row.get("disease") or {}
            disease_id = (disease.get("id") or "").strip()
            disease_name = (disease.get("name") or "").strip()
            if not disease_id or not disease_name:
                continue
            records.append(
                RawRecord(
                    record_type=RecordType.ONTOLOGY_TERM,
                    external_id=f"ot_disease_{disease_id}",
                    source_name="Open Targets Platform",
                    provenance=Provenance(
                        source_type=self.source_type(),
                        api_endpoint=OT_API_URL,
                        query_params={"drug": drug_name, "disease": disease_id},
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=self._hash(disease),
                    ),
                    data={
                        "name": disease_name,
                        "ontology_id": disease_id,
                        "term_type": "therapeutic_area",
                    },
                    identifiers={"ontology_id": disease_id},
                )
            )
        return records

    def _get_target_drugs(self) -> list[str]:
        try:
            from config import config
            names = list(getattr(config.pipeline, 'target_drug_names', []))
            if names:
                return names[:20]
        except Exception:
            pass
        return [
            "semaglutide", "tirzepatide", "empagliflozin", "dapagliflozin",
            "liraglutide", "sitagliptin", "canagliflozin", "metformin",
        ]

    @staticmethod
    def _hash(data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
