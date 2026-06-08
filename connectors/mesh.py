"""
MeSH Ontology Connector — Phase 1.

Fetches therapeutic-area and mechanism-of-action descriptors from the
NIH MeSH REST + SPARQL APIs. This is the first connector to run because
it seeds the ontology that all subsequent connectors link against.

Data sources:
    - https://id.nlm.nih.gov/mesh/{descriptorID}.json  (descriptor detail)
    - https://id.nlm.nih.gov/mesh/{conceptID}.json      (scope notes)
    - https://id.nlm.nih.gov/mesh/sparql                 (child/relation queries)

No API key required. Rate limit: be polite (0.5s between requests).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

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
from config import config

logger = logging.getLogger(__name__)

MESH_BASE = "https://id.nlm.nih.gov/mesh"
SPARQL_URL = f"{MESH_BASE}/sparql"
# The Virtuoso triplestore stores RDF resource URIs under the *http* scheme and
# segregates descriptor data into the default `…/mesh` graph. SPARQL matches URIs
# by exact string, so queries must use this http base and name the graph — using
# the https REST base (MESH_BASE) silently matches nothing.
MESH_RESOURCE_BASE = "http://id.nlm.nih.gov/mesh"
MESH_DEFAULT_GRAPH = "http://id.nlm.nih.gov/mesh"


class MeSHConnector(BaseConnector):
    """
    Fetches MeSH descriptors for therapeutic areas and mechanisms of action.

    Two-phase fetch:
        1. Therapeutic areas: target MeSH IDs + their children + siblings.
        2. Mechanisms: pharmacological-action descriptors linked to those TAs
           (GLP-1 agonists, incretins, hypoglycemic agents, etc.).

    Each descriptor produces one RawRecord with:
        - record_type: ONTOLOGY_TERM
        - external_id: MeSH descriptor ID (e.g. "D003924")
        - data: label, tree_numbers, parent, scope_note, ontology_type
        - identifiers: mesh_id, parent_mesh_id
    """

    def __init__(self, config=None, target_overrides=None):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "MarketZero/1.0 (pharma-intelligence-research)",
        })
        from config import config as default_config
        self._config = config or default_config
        self._delay = self._config.connectors.default_request_delay_seconds
        self._seen_ids: set[str] = set()

        # Allow dynamic target overrides for TA onboarding
        overrides = target_overrides or {}
        self._mesh_ids = overrides.get("mesh_ids", self._config.target_mesh_ids)
        self._mechanism_ids = overrides.get("mechanism_ids", self.MECHANISM_SEED_IDS)

    def source_type(self) -> SourceType:
        return SourceType.MESH_ONTOLOGY

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            r = self._session.get(
                f"{MESH_BASE}/D003920.json", timeout=10
            )
            elapsed = (time.time() - start) * 1000
            if r.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="MeSH API responding",
                    response_time_ms=elapsed,
                )
            return HealthCheckResult(
                healthy=False,
                source_type=self.source_type(),
                message=f"HTTP {r.status_code}",
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
        Fetch all relevant MeSH descriptors.

        Args:
            since: Ignored for MeSH (always full fetch — the ontology is small
                   and rarely changes). A full refresh is ~50-100 descriptors.

        Returns:
            List of RawRecord objects for therapeutic areas and mechanisms.
        """
        records: list[RawRecord] = []
        self._seen_ids.clear()

        # Phase 1: Therapeutic areas
        logger.info("Fetching therapeutic area descriptors...")
        ta_records = self._fetch_therapeutic_areas()
        records.extend(ta_records)
        logger.info("Fetched %d therapeutic area descriptors", len(ta_records))

        # Phase 2: Mechanisms of action
        logger.info("Fetching mechanism-of-action descriptors...")
        moa_records = self._fetch_mechanisms()
        records.extend(moa_records)
        logger.info("Fetched %d mechanism descriptors", len(moa_records))

        logger.info(
            "MeSH connector total: %d records (%d TAs, %d MOAs)",
            len(records), len(ta_records), len(moa_records),
        )
        return records

    # ------------------------------------------------------------------
    # Therapeutic areas
    # ------------------------------------------------------------------

    def _fetch_therapeutic_areas(self) -> list[RawRecord]:
        """Fetch target TAs, their children, and siblings."""
        records: list[RawRecord] = []

        for mesh_id in self._mesh_ids:
            # Fetch the target descriptor itself
            rec = self._fetch_descriptor(mesh_id, ontology_type="therapeutic_area")
            if rec:
                records.append(rec)

            # Fetch children via SPARQL
            children = self._fetch_children(mesh_id)
            for child_id in children:
                rec = self._fetch_descriptor(child_id, ontology_type="therapeutic_area")
                if rec:
                    records.append(rec)

        # Fetch parent of D003920 (Diabetes Mellitus) to get siblings
        # D003920 parent is "Glucose Metabolism Disorders" (from broaderDescriptor)
        parent_data = self._get_descriptor_json("D003920")
        if parent_data:
            parent_raw = parent_data.get("broaderDescriptor", "")
            if isinstance(parent_raw, list):
                parent_uri = parent_raw[0] if parent_raw else ""
            else:
                parent_uri = parent_raw
            if parent_uri:
                parent_id = self._extract_id(parent_uri)
                if parent_id:
                    rec = self._fetch_descriptor(parent_id, ontology_type="therapeutic_area")
                    if rec:
                        records.append(rec)
                    # Siblings = children of parent
                    siblings = self._fetch_children(parent_id)
                    for sib_id in siblings:
                        rec = self._fetch_descriptor(sib_id, ontology_type="therapeutic_area")
                        if rec:
                            records.append(rec)

        return records

    # ------------------------------------------------------------------
    # Mechanisms of action
    # ------------------------------------------------------------------

    # Key pharmacological/mechanism descriptors
    # Phase 1: Diabetes/Obesity. Phase 2: Cardiovascular/Heart Failure.
    MECHANISM_SEED_IDS = [
        # ── Diabetes / Obesity mechanisms ──
        "D000097789",  # Glucagon-Like Peptide-1 Receptor Agonists
        "D054795",     # Incretins
        "D007004",     # Hypoglycemic Agents
        "D000067757",  # Glucagon-Like Peptide-1 Receptor
        "D052216",     # Glucagon-Like Peptide 1
        "D054873",     # Dipeptidyl-Peptidase IV Inhibitors
        "D000077203",  # Sodium-Glucose Transporter 2 Inhibitors
        "D007328",     # Insulin
        "D045162",     # Thiazolidinediones
        "D008687",     # Metformin
        "D001067",     # Appetite Depressants
        # ── Phase 3 expansion: dual/multi-agonists ──
        "D005749",     # Gastric Inhibitory Polypeptide (GIP — dual GIP/GLP-1)
        "D000077582",  # Glucagon-Like Peptide-2 Receptor Agonists
        "D000068900",  # Amylin Receptor Agonists
        # ── Cardiovascular / Heart Failure mechanisms ──
        "D000806",     # Angiotensin-Converting Enzyme Inhibitors
        "D047228",     # Angiotensin II Type 1 Receptor Blockers
        "D000319",     # Adrenergic beta-Antagonists (Beta-blockers)
        "D000451",     # Mineralocorticoid Receptor Antagonists
        "D004232",     # Diuretics
        "D010726",     # Phosphodiesterase Inhibitors
        "D000077440",  # Neprilysin Inhibitors (ARNI — Entresto)
        # ── Phase 3 expansion: selective MRAs, PCSK9i, sGC stimulators ──
        "D000069059",  # PCSK9 Inhibitors (Proprotein Convertase 9)
        "D014665",     # Vasodilator Agents
        "D002121",     # Calcium Channel Blockers
        "D000068718",  # Soluble Guanylyl Cyclase Stimulators (Vericiguat)
        "D019389",     # Cytochrome P-450 CYP3A Inhibitors
    ]

    def _fetch_mechanisms(self) -> list[RawRecord]:
        """Fetch mechanism-of-action descriptors."""
        records: list[RawRecord] = []

        for mesh_id in self._mechanism_ids:
            rec = self._fetch_descriptor(mesh_id, ontology_type="mechanism_of_action")
            if rec:
                records.append(rec)

            # Also get children of each mechanism term
            children = self._fetch_children(mesh_id)
            for child_id in children:
                rec = self._fetch_descriptor(child_id, ontology_type="mechanism_of_action")
                if rec:
                    records.append(rec)

        return records

    # ------------------------------------------------------------------
    # Core API methods
    # ------------------------------------------------------------------

    def _fetch_descriptor(self, mesh_id: str, ontology_type: str) -> Optional[RawRecord]:
        """Fetch a single MeSH descriptor and its scope note, return as RawRecord."""
        if mesh_id in self._seen_ids:
            return None
        self._seen_ids.add(mesh_id)

        desc_data = self._get_descriptor_json(mesh_id)
        if not desc_data:
            return None

        # Extract fields
        label = self._get_label(desc_data)
        if not label:
            logger.warning("No label for %s, skipping", mesh_id)
            return None

        tree_numbers = self._extract_tree_numbers(desc_data)
        parent_raw = desc_data.get("broaderDescriptor", "")
        # broaderDescriptor can be a string or a list
        if isinstance(parent_raw, list):
            parent_uri = parent_raw[0] if parent_raw else ""
        else:
            parent_uri = parent_raw
        parent_id = self._extract_id(parent_uri) if parent_uri else None

        # Fetch scope note from preferred concept
        scope_note = self._fetch_scope_note(desc_data)

        api_endpoint = f"{MESH_BASE}/{mesh_id}.json"
        now = datetime.utcnow()

        return RawRecord(
            record_type=RecordType.ONTOLOGY_TERM,
            external_id=mesh_id,
            source_name="NIH MeSH",
            provenance=Provenance(
                source_type=SourceType.MESH_ONTOLOGY,
                api_endpoint=api_endpoint,
                query_params={"descriptor_id": mesh_id},
                retrieved_at=now,
                raw_response_hash=Provenance.hash_response(
                    label.encode("utf-8")
                ),
            ),
            data={
                "name": label,
                "mesh_id": mesh_id,
                "tree_numbers": tree_numbers,
                "parent_mesh_id": parent_id,
                "scope_note": scope_note,
                "ontology_type": ontology_type,
                "date_introduced": desc_data.get("dateIntroduced"),
                "last_updated": desc_data.get("lastUpdated"),
            },
            text_content=f"{label}. {scope_note}" if scope_note else label,
            identifiers={
                "mesh_id": mesh_id,
                "parent_mesh_id": parent_id,
            },
        )

    def _get_descriptor_json(self, mesh_id: str) -> Optional[dict]:
        """Fetch raw descriptor JSON from MeSH REST API."""
        url = f"{MESH_BASE}/{mesh_id}.json"
        try:
            time.sleep(self._delay)
            r = self._session.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            logger.warning("MeSH %s returned HTTP %d", mesh_id, r.status_code)
            return None
        except Exception as e:
            logger.error("Failed to fetch MeSH %s: %s", mesh_id, e)
            return None

    def _fetch_scope_note(self, desc_data: dict) -> Optional[str]:
        """Fetch the scope note (definition) from the preferred concept."""
        concept_uri = desc_data.get("preferredConcept", "")
        if not concept_uri:
            return None

        concept_id = self._extract_id(concept_uri)
        if not concept_id:
            return None

        url = f"{MESH_BASE}/{concept_id}.json"
        try:
            time.sleep(self._delay)
            r = self._session.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                scope = data.get("scopeNote", {})
                if isinstance(scope, dict):
                    return scope.get("@value")
                return str(scope) if scope else None
            return None
        except Exception as e:
            logger.warning("Failed to fetch scope note for %s: %s", concept_id, e)
            return None

    def _fetch_children(self, parent_mesh_id: str) -> list[str]:
        """Fetch child descriptor IDs via SPARQL broaderDescriptor.

        Three things are load-bearing and were previously wrong (which made this
        return zero children for every seed — the ontology never grew past its
        hand-picked seeds):
          * ``FROM <…/mesh>`` scopes the query to the default descriptor graph;
            without it the store returns no bindings.
          * the descriptor is addressed with the ``http`` resource scheme
            (``MESH_RESOURCE_BASE``), not the ``https`` REST base — SPARQL URI
            matching is exact-string.
          * no ``meshv:active`` filter (that predicate suppressed all rows).
        """
        query = f"""
            PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
            SELECT DISTINCT ?d FROM <{MESH_DEFAULT_GRAPH}> WHERE {{
                ?d meshv:broaderDescriptor <{MESH_RESOURCE_BASE}/{parent_mesh_id}> .
            }}
        """
        try:
            time.sleep(self._delay)
            r = self._session.get(
                SPARQL_URL,
                params={"query": query, "format": "JSON"},
                timeout=30,
            )
            if r.status_code != 200:
                logger.warning(
                    "SPARQL children query for %s returned %d",
                    parent_mesh_id, r.status_code,
                )
                return []

            bindings = r.json().get("results", {}).get("bindings", [])
            child_ids = []
            for b in bindings:
                uri = b.get("d", {}).get("value", "")
                cid = self._extract_id(uri)
                if cid:
                    child_ids.append(cid)
            return child_ids

        except Exception as e:
            logger.error("SPARQL children query failed for %s: %s", parent_mesh_id, e)
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_id(uri: str) -> Optional[str]:
        """Extract MeSH ID from URI like 'http://id.nlm.nih.gov/mesh/D003924'."""
        if not uri:
            return None
        return uri.rstrip("/").split("/")[-1]

    @staticmethod
    def _get_label(data: dict) -> Optional[str]:
        """Extract label from descriptor or concept JSON."""
        label = data.get("label", {})
        if isinstance(label, dict):
            return label.get("@value")
        return str(label) if label else None

    @staticmethod
    def _extract_tree_numbers(data: dict) -> list[str]:
        """Extract tree number strings from descriptor JSON."""
        tn_raw = data.get("treeNumber", [])
        if isinstance(tn_raw, str):
            tn_raw = [tn_raw]
        tree_numbers = []
        for tn in tn_raw:
            if isinstance(tn, str):
                # Extract just the tree number from URI
                tree_numbers.append(tn.split("/")[-1])
            elif isinstance(tn, dict):
                tree_numbers.append(tn.get("@value", tn.get("value", str(tn))))
        return tree_numbers
