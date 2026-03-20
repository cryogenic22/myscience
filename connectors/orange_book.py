"""
FDA Orange Book Connector.

Fetches drug approval data from the openFDA drugsfda API. For each drug
application, produces:
  - DRUG records (one per application)
  - PATENT records (from products[].active_ingredients)
  - REGULATORY_MILESTONE records (from submissions[])

This is the highest-priority connector because it populates `drugs` and
`companies` tables that all other connectors link against.

API docs: https://open.fda.gov/apis/drug/drugsfda/
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

import requests

from connectors.base import (
    BaseConnector,
    ConnectorError,
    HealthCheckResult,
    Provenance,
    RawRecord,
    RecordType,
    SourceType,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.fda.gov/drug/drugsfda.json"

# EPC (Established Pharmacologic Class) terms for our target drug classes.
# These map to pharm_class_epc in the openFDA fields.
TARGET_PHARM_CLASSES = [
    # ── Diabetes / Obesity ──
    "Glucagon-Like Peptide-1 (GLP-1) Receptor Agonist [EPC]",
    "Dipeptidyl Peptidase 4 Inhibitor [EPC]",
    "Sodium-Glucose Transporter 2 Inhibitor [EPC]",
    "Insulin [EPC]",
    "Biguanide [EPC]",
    "Thiazolidinedione [EPC]",
    "Meglitinide Analog [EPC]",
    "Alpha-glucosidase Inhibitor [EPC]",
    "Amylin Analog [EPC]",
    # ── Cardiovascular / Heart Failure ──
    "Angiotensin-Converting Enzyme Inhibitor [EPC]",
    "Angiotensin 2 Receptor Blocker [EPC]",
    "Beta-Adrenergic Blocker [EPC]",
    "Neprilysin Inhibitor [EPC]",
    "Aldosterone Antagonist [EPC]",
    "Loop Diuretic [EPC]",
    "HCN Channel Blocker [EPC]",
    "Soluble Guanylate Cyclase Stimulator [EPC]",
    "Non-steroidal Mineralocorticoid Receptor Antagonist [EPC]",
]


class OrangeBookConnector(BaseConnector):
    """
    Fetches drug application data from the FDA drugsfda API.

    Search strategy: query by openfda.pharm_class_epc for each target
    pharmacologic class. Deduplicate by application_number.
    """

    def __init__(self, config=None, target_overrides=None):
        self.config = config
        self.api_key = ""
        self.request_delay = 0.5
        if config:
            self.api_key = config.connectors.openfda_api_key
            self.request_delay = config.connectors.default_request_delay_seconds
        self.session = requests.Session()

        # Allow dynamic target overrides for TA onboarding
        overrides = target_overrides or {}
        self._epc_classes = overrides.get("epc_classes", TARGET_PHARM_CLASSES)

    def source_type(self) -> SourceType:
        return SourceType.FDA_ORANGE_BOOK

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            resp = self.session.get(
                API_BASE,
                params={"search": 'openfda.brand_name:"OZEMPIC"', "limit": 1},
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="FDA drugsfda API reachable",
                    response_time_ms=elapsed,
                )
            return HealthCheckResult(
                healthy=False,
                source_type=self.source_type(),
                message=f"HTTP {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                source_type=self.source_type(),
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """
        Fetch drug applications for all target pharmacologic classes.

        Returns DRUG + REGULATORY_MILESTONE records. Patent data comes
        from separate product-level parsing.
        """
        records: list[RawRecord] = []
        seen_apps: set[str] = set()

        for pharm_class in self._epc_classes:
            logger.info("Fetching FDA drugs for pharm_class: %s", pharm_class)
            try:
                apps = self._search_by_pharm_class(pharm_class)
            except Exception as e:
                logger.error("Error fetching %s: %s", pharm_class, e)
                continue

            for app in apps:
                app_number = app.get("application_number", "")
                if not app_number or app_number in seen_apps:
                    continue
                seen_apps.add(app_number)

                try:
                    app_records = self._parse_application(app, pharm_class)
                    records.extend(app_records)
                except Exception as e:
                    logger.error("Error parsing app %s: %s", app_number, e)

            time.sleep(self.request_delay)

        logger.info(
            "Orange Book fetch complete: %d applications → %d records",
            len(seen_apps), len(records),
        )
        return records

    def _search_by_pharm_class(self, pharm_class: str) -> list[dict]:
        """Search FDA API by EPC pharmacologic class, paginate through all results."""
        all_results = []
        skip = 0
        limit = 100

        while True:
            params: dict[str, Any] = {
                "search": f'openfda.pharm_class_epc:"{pharm_class}"',
                "limit": limit,
                "skip": skip,
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self.session.get(API_BASE, params=params, timeout=30)

            if resp.status_code == 404:
                # No results for this class
                break
            if resp.status_code != 200:
                logger.warning(
                    "FDA API returned %d for %s (skip=%d)",
                    resp.status_code, pharm_class, skip,
                )
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += limit
            if skip >= total or skip >= 1000:
                # FDA API caps skip at 25000, but we limit to 1000 per class
                break

            time.sleep(self.request_delay)

        return all_results

    def _parse_application(self, app: dict, pharm_class: str) -> list[RawRecord]:
        """
        Parse a single FDA application into RawRecord objects.

        Produces:
        - 1 DRUG record per application
        - N REGULATORY_MILESTONE records (one per submission)
        """
        records: list[RawRecord] = []
        now = datetime.utcnow()

        app_number = app.get("application_number", "")
        sponsor = app.get("sponsor_name", "")
        openfda = app.get("openfda", {})
        products = app.get("products", [])
        submissions = app.get("submissions", [])

        # Build response hash
        import json
        raw_bytes = json.dumps(app, sort_keys=True).encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        api_url = f"{API_BASE}?search=application_number:{app_number}"

        prov = Provenance(
            source_type=SourceType.FDA_ORANGE_BOOK,
            api_endpoint=api_url,
            query_params={"application_number": app_number, "pharm_class": pharm_class},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # ---- DRUG record ----
        # Pick the most informative product variant (prefer Prescription, non-discontinued)
        best_product = self._pick_best_product(products)

        brand_names = openfda.get("brand_name", [])
        generic_names = openfda.get("generic_name", [])
        rxcuis = openfda.get("rxcui", [])

        # Find earliest approval date from submissions
        approval_date = self._find_approval_date(submissions)

        drug_data = {
            "application_number": app_number,
            "brand_name": brand_names[0] if brand_names else (best_product.get("brand_name") if best_product else None),
            "generic_name": generic_names[0] if generic_names else None,
            "company_name": sponsor,
            "approval_date": approval_date,
            "pharm_class": pharm_class,
            "dosage_form": best_product.get("dosage_form") if best_product else None,
            "route": best_product.get("route") if best_product else None,
            "marketing_status": best_product.get("marketing_status") if best_product else None,
            "rxcui": rxcuis[0] if rxcuis else None,
        }

        # Extract identifiers for entity resolution
        identifiers: dict[str, Any] = {
            "nda_number": app_number,
            "company_name": sponsor,
        }
        generic = generic_names[0] if generic_names else None
        if generic:
            identifiers["generic_name"] = generic

        mesh_ids = openfda.get("nui", [])
        if mesh_ids:
            identifiers["mesh_ids"] = mesh_ids

        text_content = self._build_drug_text(drug_data, openfda)

        records.append(RawRecord(
            record_type=RecordType.DRUG,
            external_id=app_number,
            source_name="FDA Orange Book (drugsfda)",
            provenance=prov,
            data=drug_data,
            text_content=text_content,
            identifiers=identifiers,
        ))

        # ---- PATENT records ----
        seen_patents: set[str] = set()
        for product in products:
            # openFDA products can contain patent information
            p_number = product.get("patent_number")
            p_expiry = product.get("patent_expiry_date")
            p_type = product.get("patent_type")

            if not p_number:
                continue
            if p_number in seen_patents:
                continue
            seen_patents.add(p_number)

            patent_data = {
                "application_number": app_number,
                "patent_number": p_number,
                "patent_expiry_date": p_expiry,
                "patent_type": p_type or "drug",
                "applicant_holder": sponsor,
                "generic_name": generic_names[0] if generic_names else None,
            }

            patent_ext_id = f"{app_number}|PAT|{p_number}"

            records.append(RawRecord(
                record_type=RecordType.PATENT,
                external_id=patent_ext_id,
                source_name="FDA Orange Book (drugsfda)",
                provenance=prov,
                data=patent_data,
                identifiers={"nda_number": app_number, "patent_number": p_number},
            ))

        # ---- REGULATORY_MILESTONE records ----
        for sub in submissions:
            sub_type = sub.get("submission_type", "")
            sub_number = sub.get("submission_number", "")
            sub_status = sub.get("submission_status", "")
            sub_date = sub.get("submission_status_date", "")
            review_priority = sub.get("review_priority", "")

            # Extract document URL if available
            doc_url = None
            app_docs = sub.get("application_docs", [])
            for doc in app_docs:
                if doc.get("type") == "Label":
                    doc_url = doc.get("url")
                    break
            if not doc_url and app_docs:
                doc_url = app_docs[0].get("url")

            milestone_data = {
                "application_number": app_number,
                "submission_type": sub_type,
                "submission_number": sub_number,
                "submission_status": sub_status,
                "submission_status_date": sub_date,
                "review_priority": review_priority,
                "document_url": doc_url,
            }

            ext_id = f"{app_number}|{sub_type}{sub_number}"

            records.append(RawRecord(
                record_type=RecordType.REGULATORY_MILESTONE,
                external_id=ext_id,
                source_name="FDA Orange Book (drugsfda)",
                provenance=prov,
                data=milestone_data,
                identifiers={"nda_number": app_number},
            ))

        return records

    def _pick_best_product(self, products: list[dict]) -> Optional[dict]:
        """Pick the most relevant product variant from the products list."""
        if not products:
            return None

        # Prefer Prescription over Discontinued
        for p in products:
            if p.get("marketing_status") == "Prescription":
                return p

        # Fall back to first non-discontinued
        for p in products:
            if p.get("marketing_status") != "Discontinued":
                return p

        return products[0]

    def _find_approval_date(self, submissions: list[dict]) -> Optional[str]:
        """Find the original approval date from submissions."""
        for sub in submissions:
            if (
                sub.get("submission_type") == "ORIG"
                and sub.get("submission_status") == "AP"
            ):
                return sub.get("submission_status_date")

        # Fall back to earliest AP date
        ap_dates = []
        for sub in submissions:
            if sub.get("submission_status") == "AP":
                d = sub.get("submission_status_date")
                if d:
                    ap_dates.append(d)
        return min(ap_dates) if ap_dates else None

    def _build_drug_text(self, data: dict, openfda: dict) -> str:
        """Build free text for embedding from drug data."""
        parts = []
        if data.get("brand_name"):
            parts.append(f"Brand: {data['brand_name']}")
        if data.get("generic_name"):
            parts.append(f"Generic: {data['generic_name']}")
        if data.get("company_name"):
            parts.append(f"Company: {data['company_name']}")
        if data.get("pharm_class"):
            parts.append(f"Class: {data['pharm_class']}")
        if data.get("dosage_form"):
            parts.append(f"Form: {data['dosage_form']}")
        if data.get("route"):
            parts.append(f"Route: {data['route']}")

        # Add all pharm classes
        for key in ("pharm_class_epc", "pharm_class_moa", "pharm_class_cs"):
            classes = openfda.get(key, [])
            if classes:
                parts.append(f"{key}: {', '.join(classes)}")

        return ". ".join(parts)
