"""
ClinicalTrials.gov Connector (v2 API).

Fetches clinical trial data for drugs in our target therapeutic areas.
Produces:
  - TRIAL records (one per study)
  - TRIAL_OUTCOME records (primary/secondary endpoints)
  - TRIAL_LOCATION records (geographic sites)
  - INVESTIGATOR records (principal investigators)

API docs: https://clinicaltrials.gov/data-api/api
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

API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Drug names to search for — active ingredients in our target therapeutic areas.
TARGET_DRUG_NAMES = [
    # ── Diabetes / Obesity ──
    "semaglutide",
    "liraglutide",
    "tirzepatide",
    "dulaglutide",
    "exenatide",
    "lixisenatide",
    "empagliflozin",
    "dapagliflozin",
    "canagliflozin",
    "ertugliflozin",
    "sitagliptin",
    "linagliptin",
    "saxagliptin",
    "alogliptin",
    "metformin",
    "pioglitazone",
    "rosiglitazone",
    "insulin glargine",
    "insulin lispro",
    "insulin aspart",
    "insulin degludec",
    # ── Cardiovascular / Heart Failure ──
    "sacubitril",       # Entresto (ARNI)
    "valsartan",        # ARB — component of Entresto
    "finerenone",       # Non-steroidal MRA (Kerendia)
    "vericiguat",       # sGC stimulator (Verquvo)
    "ivabradine",       # If channel blocker (Corlanor)
    "carvedilol",       # Beta-blocker
    "metoprolol",       # Beta-blocker
    "enalapril",        # ACE inhibitor
    "losartan",         # ARB
    "spironolactone",   # MRA
    "eplerenone",       # MRA
]

# Conditions to search
TARGET_CONDITIONS = [
    # ── Diabetes / Obesity ──
    "diabetes mellitus type 2",
    "obesity",
    # ── Cardiovascular / Heart Failure ──
    "heart failure",
    "cardiovascular disease",
    "heart failure with reduced ejection fraction",
    "heart failure with preserved ejection fraction",
]


class ClinicalTrialsConnector(BaseConnector):
    """
    Fetches clinical trial data from ClinicalTrials.gov v2 API.

    Strategy: For each target drug + condition combination, search for
    interventional studies. Deduplicate by NCT ID.
    """

    def __init__(self, config=None):
        self.config = config
        self.request_delay = 0.5
        if config:
            self.request_delay = config.connectors.default_request_delay_seconds
        self.session = requests.Session()

    def source_type(self) -> SourceType:
        return SourceType.CLINICAL_TRIALS_GOV

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            resp = self.session.get(
                API_BASE,
                params={"query.cond": "diabetes", "pageSize": 1},
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="ClinicalTrials.gov v2 API reachable",
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
        """Fetch clinical trials for target drugs and conditions."""
        records: list[RawRecord] = []
        seen_ncts: set[str] = set()

        for drug in TARGET_DRUG_NAMES:
            for condition in TARGET_CONDITIONS:
                logger.info("Searching trials: %s + %s", drug, condition)
                try:
                    studies = self._search_studies(drug, condition)
                except Exception as e:
                    logger.error("Error searching %s/%s: %s", drug, condition, e)
                    continue

                for study in studies:
                    nct_id = self._get_nct_id(study)
                    if not nct_id or nct_id in seen_ncts:
                        continue
                    seen_ncts.add(nct_id)

                    try:
                        study_records = self._parse_study(study)
                        records.extend(study_records)
                    except Exception as e:
                        logger.error("Error parsing %s: %s", nct_id, e)

        logger.info(
            "ClinicalTrials.gov fetch complete: %d trials → %d records",
            len(seen_ncts), len(records),
        )
        return records

    def _search_studies(self, drug: str, condition: str) -> list[dict]:
        """Search for studies matching drug + condition, paginate through results."""
        all_studies = []
        page_token = None

        while True:
            params: dict[str, Any] = {
                "query.cond": condition,
                "query.intr": drug,
                "filter.overallStatus": "NOT_YET_RECRUITING,RECRUITING,ENROLLING_BY_INVITATION,ACTIVE_NOT_RECRUITING,COMPLETED,TERMINATED,SUSPENDED,WITHDRAWN",
                "pageSize": 100,
                "fields": (
                    "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,"
                    "LeadSponsorName,Condition,InterventionName,InterventionType,"
                    "StartDate,PrimaryCompletionDate,CompletionDate,"
                    "EnrollmentCount,EnrollmentType,WhyStopped,"
                    "DetailedDescription,BriefSummary,StudyType,"
                    "EligibilityCriteria,CollaboratorName,"
                    "PrimaryOutcomeMeasure,PrimaryOutcomeDescription,PrimaryOutcomeTimeFrame,"
                    "SecondaryOutcomeMeasure,SecondaryOutcomeTimeFrame,"
                    "LocationFacility,LocationCity,LocationState,LocationCountry,LocationStatus,"
                    "OverallOfficialName,OverallOfficialAffiliation,OverallOfficialRole"
                ),
            }
            if page_token:
                params["pageToken"] = page_token

            resp = self.session.get(API_BASE, params=params, timeout=30)

            if resp.status_code != 200:
                logger.warning("CT.gov API returned %d", resp.status_code)
                break

            data = resp.json()
            studies = data.get("studies", [])
            if not studies:
                break

            all_studies.extend(studies)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            # Cap at 500 studies per search to keep total manageable
            if len(all_studies) >= 500:
                break

            time.sleep(self.request_delay)

        return all_studies

    def _get_nct_id(self, study: dict) -> Optional[str]:
        """Extract NCT ID from study data."""
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        return ident.get("nctId")

    def _parse_study(self, study: dict) -> list[RawRecord]:
        """Parse a study into TRIAL + TRIAL_OUTCOME + TRIAL_LOCATION + INVESTIGATOR records."""
        records: list[RawRecord] = []
        now = datetime.utcnow()
        proto = study.get("protocolSection", {})

        ident = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        desc = proto.get("descriptionModule", {})
        conditions_mod = proto.get("conditionsModule", {})
        arms = proto.get("armsInterventionsModule", {})
        outcomes = proto.get("outcomesModule", {})
        eligibility = proto.get("eligibilityModule", {})
        contacts = proto.get("contactsLocationsModule", {})

        nct_id = ident.get("nctId", "")
        if not nct_id:
            return records

        # Build provenance
        import json
        raw_bytes = json.dumps(study, sort_keys=True).encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        api_url = f"{API_BASE}?query.term={nct_id}"
        prov = Provenance(
            source_type=SourceType.CLINICAL_TRIALS_GOV,
            api_endpoint=api_url,
            query_params={"nctId": nct_id},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # ---- TRIAL record ----
        sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "")
        collaborators = [c.get("name", "") for c in sponsor_mod.get("collaborators", [])]

        conditions = conditions_mod.get("conditions", [])

        # Extract interventions
        interventions = []
        for intr in arms.get("interventions", []):
            name = intr.get("name", "")
            itype = intr.get("type", "")
            if name:
                interventions.append(f"{itype}: {name}" if itype else name)

        enrollment_info = design.get("enrollmentInfo", {})
        enrollment_count = enrollment_info.get("count")

        start_date = status_mod.get("startDateStruct", {}).get("date")
        completion_date = status_mod.get("completionDateStruct", {}).get("date")
        primary_comp_date = status_mod.get("primaryCompletionDateStruct", {}).get("date")

        detailed_desc = desc.get("detailedDescription", desc.get("briefSummary", ""))

        trial_data = {
            "nct_id": nct_id,
            "brief_title": ident.get("briefTitle", ""),
            "official_title": ident.get("officialTitle", ""),
            "overall_status": status_mod.get("overallStatus", ""),
            "phase": self._normalize_phase(design.get("phases", [])),
            "lead_sponsor_name": sponsor,
            "conditions": ", ".join(conditions) if conditions else None,
            "interventions": ", ".join(interventions) if interventions else None,
            "start_date": start_date,
            "completion_date": completion_date,
            "primary_completion_date": primary_comp_date,
            "enrollment_target": enrollment_count,
            "actual_enrollment": enrollment_count if enrollment_info.get("type") == "ACTUAL" else None,
            "why_stopped": status_mod.get("whyStopped"),
            "detailed_description": detailed_desc,
            "study_type": design.get("studyType"),
            "eligibility_criteria": eligibility.get("eligibilityCriteria"),
            "collaborator_names": collaborators if collaborators else None,
        }

        # Identifiers for entity resolution
        identifiers: dict[str, Any] = {"nct_id": nct_id}
        if sponsor:
            identifiers["sponsor_name"] = sponsor

        # Try to find generic drug name from interventions
        for intr in arms.get("interventions", []):
            if intr.get("type") == "DRUG":
                identifiers["generic_name"] = intr.get("name", "").lower()
                break

        text_content = f"{ident.get('briefTitle', '')}. {detailed_desc or ''}"

        records.append(RawRecord(
            record_type=RecordType.TRIAL,
            external_id=nct_id,
            source_name="ClinicalTrials.gov",
            provenance=prov,
            data=trial_data,
            text_content=text_content,
            identifiers=identifiers,
        ))

        # ---- TRIAL_OUTCOME records ----
        for outcome_type, key in [
            ("PRIMARY", "primaryOutcomes"),
            ("SECONDARY", "secondaryOutcomes"),
            ("OTHER", "otherOutcomes"),
        ]:
            for outcome in outcomes.get(key, []):
                measure = outcome.get("measure", "")
                if not measure:
                    continue

                outcome_data = {
                    "nct_id": nct_id,
                    "outcome_type": outcome_type,
                    "measure": measure,
                    "time_frame": outcome.get("timeFrame"),
                    "description": outcome.get("description"),
                }

                ext_id = f"{nct_id}|{outcome_type}|{measure[:50]}"
                records.append(RawRecord(
                    record_type=RecordType.TRIAL_OUTCOME,
                    external_id=ext_id,
                    source_name="ClinicalTrials.gov",
                    provenance=prov,
                    data=outcome_data,
                    identifiers={"nct_id": nct_id},
                ))

        # ---- TRIAL_LOCATION records ----
        for loc in contacts.get("locations", []):
            country = loc.get("country", "")
            if not country:
                continue

            location_data = {
                "nct_id": nct_id,
                "facility_name": loc.get("facility"),
                "city": loc.get("city"),
                "state": loc.get("state"),
                "country": country,
                "location_status": loc.get("status"),
            }

            facility = loc.get("facility", "unknown")
            ext_id = f"{nct_id}|{country}|{facility[:30]}"
            records.append(RawRecord(
                record_type=RecordType.TRIAL_LOCATION,
                external_id=ext_id,
                source_name="ClinicalTrials.gov",
                provenance=prov,
                data=location_data,
                identifiers={"nct_id": nct_id},
            ))

        # ---- INVESTIGATOR records ----
        for official in contacts.get("overallOfficials", []):
            name = official.get("name", "")
            if not name or official.get("role") != "PRINCIPAL_INVESTIGATOR":
                continue

            inv_data = {
                "investigator_name": name,
                "investigator_affiliation": official.get("affiliation"),
                "trial_nct_id": nct_id,
            }

            ext_id = f"INV|{nct_id}|{name[:40]}"
            records.append(RawRecord(
                record_type=RecordType.INVESTIGATOR,
                external_id=ext_id,
                source_name="ClinicalTrials.gov",
                provenance=prov,
                data=inv_data,
                identifiers={"investigator_name": name},
            ))

        return records

    def _normalize_phase(self, phases: list[str]) -> Optional[str]:
        """Normalize phase list to a single string."""
        if not phases:
            return None
        # v2 API returns phases as list: ["PHASE3"], ["PHASE2", "PHASE3"], etc.
        phase_str = ", ".join(phases)
        # Clean up formatting
        return phase_str.replace("PHASE", "Phase ").replace("NA", "N/A")
