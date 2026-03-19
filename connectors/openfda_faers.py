"""
OpenFDA FAERS (FDA Adverse Event Reporting System) Connector.

Fetches adverse event reports from the openFDA drug/event API for target drugs.
Each report may contain multiple reactions; we produce one ADVERSE_EVENT record
per report (with the primary/most-serious reaction).

Produces:
  - ADVERSE_EVENT records (one per safety report)

API docs: https://open.fda.gov/apis/drug/event/
Rate limits:
  - Without API key: 240 requests/minute, 1000/day
  - With API key: 240 requests/minute, 120000/day
"""

from __future__ import annotations

import json
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

API_BASE = "https://api.fda.gov/drug/event.json"

# Target drugs to search in FAERS — searched by generic_name in patient.drug.openfda fields.
TARGET_DRUGS = [
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "exenatide",
    "empagliflozin", "dapagliflozin", "canagliflozin",
    "sitagliptin", "linagliptin", "saxagliptin",
    "metformin", "pioglitazone",
    "sacubitril", "valsartan", "finerenone", "vericiguat", "ivabradine",
    "carvedilol", "metoprolol", "enalapril", "losartan",
    "spironolactone", "eplerenone",
]

MAX_REPORTS_PER_DRUG = 100  # Keep total volume manageable per run


class OpenFDAFAERSConnector(BaseConnector):
    """
    Fetches adverse event reports from FDA FAERS via openFDA.

    Strategy: For each target drug, query by patient.drug.openfda.generic_name,
    sorted by receivedate descending. Deduplicate by safety_report_id.
    """

    def __init__(self, config=None):
        self.config = config
        self.api_key = ""
        self.request_delay = 0.25  # ~4 req/sec (conservative under 240/min)
        if config:
            self.api_key = config.connectors.openfda_api_key
            self.request_delay = config.connectors.default_request_delay_seconds
        self.session = requests.Session()

    def source_type(self) -> SourceType:
        return SourceType.OPENFDA_FAERS

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            params: dict[str, Any] = {
                "search": 'patient.drug.openfda.generic_name:"semaglutide"',
                "limit": 1,
            }
            if self.api_key:
                params["api_key"] = self.api_key
            resp = self.session.get(API_BASE, params=params, timeout=15)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="openFDA FAERS API reachable",
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
        Fetch adverse event reports for all target drugs.

        Args:
            since: If provided, only fetch reports received after this date
                   (uses receivedate field for incremental fetches).
        """
        records: list[RawRecord] = []
        seen_report_ids: set[str] = set()

        for drug_name in TARGET_DRUGS:
            logger.info("FAERS search: %s", drug_name)
            try:
                reports = self._search_reports(drug_name, since)
            except Exception as e:
                logger.error("FAERS search failed for %s: %s", drug_name, e)
                continue

            for report in reports:
                report_id = report.get("safetyreportid", "")
                if not report_id or report_id in seen_report_ids:
                    continue
                seen_report_ids.add(report_id)

                try:
                    record = self._parse_report(report, drug_name)
                    if record:
                        records.append(record)
                except Exception as e:
                    logger.error("Error parsing FAERS report %s: %s", report_id, e)

        logger.info(
            "FAERS fetch complete: %d unique reports -> %d records",
            len(seen_report_ids), len(records),
        )
        return records

    def _search_reports(self, drug_name: str, since: Optional[datetime] = None) -> list[dict]:
        """Search FAERS for adverse event reports by drug generic name."""
        all_results: list[dict] = []
        skip = 0
        limit = 100

        # Build search query
        search = f'patient.drug.openfda.generic_name:"{drug_name}"'
        if since:
            date_str = since.strftime("%Y%m%d")
            search += f"+AND+receivedate:[{date_str}+TO+20991231]"

        while True:
            params: dict[str, Any] = {
                "search": search,
                "sort": "receivedate:desc",
                "limit": limit,
                "skip": skip,
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self.session.get(API_BASE, params=params, timeout=30)

            if resp.status_code == 404:
                # No results for this drug
                break
            if resp.status_code != 200:
                logger.warning(
                    "FAERS API returned %d for %s (skip=%d)",
                    resp.status_code, drug_name, skip,
                )
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += limit
            if skip >= total or len(all_results) >= MAX_REPORTS_PER_DRUG:
                break

            time.sleep(self.request_delay)

        return all_results[:MAX_REPORTS_PER_DRUG]

    def _parse_report(self, report: dict, searched_drug: str) -> Optional[RawRecord]:
        """Parse a single FAERS adverse event report into a RawRecord."""
        now = datetime.utcnow()

        report_id = report.get("safetyreportid", "")
        if not report_id:
            return None

        # Patient demographics
        patient = report.get("patient", {})
        patient_age = None
        patient_age_raw = patient.get("patientonsetage")
        patient_age_unit = patient.get("patientonsetageunit")
        if patient_age_raw:
            try:
                age_val = float(patient_age_raw)
                # Convert to years if needed (unit codes: 800=decade, 801=year,
                # 802=month, 803=week, 804=day, 805=hour)
                if patient_age_unit == "801" or patient_age_unit is None:
                    patient_age = age_val
                elif patient_age_unit == "800":
                    patient_age = age_val * 10
                elif patient_age_unit == "802":
                    patient_age = age_val / 12
                elif patient_age_unit == "803":
                    patient_age = age_val / 52
                elif patient_age_unit == "804":
                    patient_age = age_val / 365
                else:
                    patient_age = age_val
            except (ValueError, TypeError):
                pass

        patient_sex_code = patient.get("patientsex")
        patient_sex_map = {"1": "male", "2": "female", "0": "unknown"}
        patient_sex = patient_sex_map.get(patient_sex_code)

        # Reactions — pick the primary reaction (first one)
        reactions = patient.get("reaction", [])
        primary_reaction = ""
        reaction_meddra_pt = None
        if reactions:
            primary_reaction = reactions[0].get("reactionmeddrapt", "")
            reaction_meddra_pt = primary_reaction

        if not primary_reaction:
            # Skip reports with no reaction data
            return None

        # Outcomes
        outcome_codes = report.get("serious", "")
        outcome_parts = []
        if report.get("seriousnessdeath") == "1":
            outcome_parts.append("death")
        if report.get("seriousnesshospitalization") == "1":
            outcome_parts.append("hospitalization")
        if report.get("seriousnesslifethreatening") == "1":
            outcome_parts.append("life_threatening")
        if report.get("seriousnessdisabling") == "1":
            outcome_parts.append("disability")
        if report.get("seriousnesscongenitalanomali") == "1":
            outcome_parts.append("congenital_anomaly")
        if report.get("seriousnessother") == "1":
            outcome_parts.append("other_serious")
        outcome = ", ".join(outcome_parts) if outcome_parts else None

        # Severity
        serious = report.get("serious", "")
        severity = "serious" if serious == "1" else "not_serious"

        # Report date
        receive_date = report.get("receivedate", "")
        report_date = None
        if receive_date and len(receive_date) == 8:
            report_date = f"{receive_date[:4]}-{receive_date[4:6]}-{receive_date[6:8]}"

        # Reporter type
        primary_source = report.get("primarysource", {})
        reporter_qual = primary_source.get("qualification")
        reporter_type_map = {
            "1": "physician",
            "2": "pharmacist",
            "3": "other_health_professional",
            "4": "lawyer",
            "5": "consumer",
        }
        reporter_type = reporter_type_map.get(reporter_qual)

        # Build provenance
        raw_bytes = json.dumps(report, sort_keys=True).encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        api_url = f'{API_BASE}?search=safetyreportid:"{report_id}"'
        prov = Provenance(
            source_type=SourceType.OPENFDA_FAERS,
            api_endpoint=api_url,
            query_params={"safetyreportid": report_id, "searched_drug": searched_drug},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Build data payload
        ae_data = {
            "report_id": report_id,
            "drug_name": searched_drug,
            "reaction": primary_reaction,
            "reaction_meddra_pt": reaction_meddra_pt,
            "all_reactions": [r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")],
            "outcome": outcome,
            "severity": severity,
            "report_date": report_date,
            "patient_age": round(patient_age, 1) if patient_age is not None else None,
            "patient_sex": patient_sex,
            "reporter_type": reporter_type,
            "reporter_country": primary_source.get("reportercountry"),
            "sender_organization": report.get("sender", {}).get("senderorganization"),
            "duplicate": report.get("duplicate"),
            "companynumb": report.get("companynumb"),
        }

        # All reactions as text for embedding
        all_reaction_text = "; ".join(
            r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")
        )
        text_content = (
            f"Adverse event for {searched_drug}: {all_reaction_text}. "
            f"Outcome: {outcome or 'none reported'}. Severity: {severity}."
        )

        identifiers: dict[str, Any] = {
            "generic_name": searched_drug,
            "report_id": report_id,
        }

        return RawRecord(
            record_type=RecordType.ADVERSE_EVENT,
            external_id=report_id,
            source_name="FDA FAERS (openFDA)",
            provenance=prov,
            data=ae_data,
            text_content=text_content,
            identifiers=identifiers,
        )
