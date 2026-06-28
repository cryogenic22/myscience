"""DataHub L2 (docs/SPEC_DATA_HUB.md §5.1) — connector-type taxonomy + source
onboarding lifecycle.

Two concerns, both additive over the existing `sources` registry (055):

1. **Connector-type taxonomy** — every source declares *how* it is fetched
   (API_REST / RSS / CSV_FILE / WEB_SCRAPE / WAREHOUSE / MANUAL) without a
   code-side enum edit. The taxonomy table (migration 096) is the DB truth;
   `CONNECTOR_TYPE_NAMES` here mirrors it for offline validation (a test asserts
   they stay in sync).

2. **Onboarding lifecycle** — a source moves through
   `draft → test → staged → prod → paused → retired`. The legal transitions are a
   small state machine enforced here (`validate_transition`); the DB column only
   constrains the *set* of statuses. This makes onboarding a tracked product
   step, not a binary `active` flag flip.

Pure helpers (transition validation, status constants) are testable in isolation,
mirroring `source_registry.py`'s pure dimension scorers. DB-backed functions take
a `db` with `fetch_one(sql, params)` / `fetch_all(sql, params)` like the rest of
the services layer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Connector types that have a Phase-1 runtime connector (config-driven generic
# connectors). A source of one of these types, once promoted to `prod`, is run by
# the scheduler's dynamic pass. WEB_SCRAPE / WAREHOUSE / MANUAL persist + draft but
# do not auto-run yet.
RUNTIME_CONNECTOR_TYPES: tuple[str, ...] = ("API_REST", "CSV_FILE", "RSS")

# Shared SELECT column list so the onboarding read paths cannot drift apart.
_ONBOARDING_COLS = (
    "source_id, status, owner, contact, go_live_date, escalation, "
    "config, field_mappings, record_type, trust_tier, must_capture, license, "
    "cadence, created_at, updated_at"
)


# ────────────────────────────────────────────────────────────────────
# Taxonomy constants (mirror migration 096's seed — kept in sync by a test)
# ────────────────────────────────────────────────────────────────────

CONNECTOR_TYPE_NAMES: tuple[str, ...] = (
    "API_REST", "RSS", "CSV_FILE", "WEB_SCRAPE", "WAREHOUSE", "MANUAL",
)


# ────────────────────────────────────────────────────────────────────
# Onboarding lifecycle state machine
# ────────────────────────────────────────────────────────────────────

INITIAL_STATUS = "draft"

ONBOARDING_STATUSES: tuple[str, ...] = (
    "draft", "test", "staged", "prod", "paused", "retired",
)

# Legal forward/backward transitions. `retired` is terminal. Any source can be
# retired from any live state; a paused source resumes to prod.
_TRANSITIONS: dict[str, set[str]] = {
    "draft":   {"test", "retired"},
    "test":    {"draft", "staged", "retired"},
    "staged":  {"test", "prod", "retired"},
    "prod":    {"paused", "retired"},
    "paused":  {"prod", "retired"},
    "retired": set(),
}


class InvalidTransition(ValueError):
    """Raised when an onboarding status change is not a legal transition."""


class UnknownConnectorType(ValueError):
    """Raised when a connector_type is not a member of the taxonomy."""


class OnboardingNotFound(Exception):
    pass


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """True iff `from_status → to_status` is a legal lifecycle transition.

    A no-op (`x → x`) is NOT a transition (callers should detect idempotency
    before calling). Unknown statuses are never valid.
    """
    if from_status not in _TRANSITIONS or to_status not in ONBOARDING_STATUSES:
        return False
    return to_status in _TRANSITIONS[from_status]


def validate_transition(from_status: str, to_status: str) -> None:
    """Raise InvalidTransition unless the transition is legal."""
    if to_status not in ONBOARDING_STATUSES:
        raise InvalidTransition(
            f"unknown status {to_status!r}; must be one of {list(ONBOARDING_STATUSES)}"
        )
    if not is_valid_transition(from_status, to_status):
        allowed = sorted(_TRANSITIONS.get(from_status, set()))
        raise InvalidTransition(
            f"{from_status!r} → {to_status!r} is not allowed "
            f"(from {from_status!r} you may go to {allowed or 'nowhere — terminal'})"
        )


# ────────────────────────────────────────────────────────────────────
# Dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class ConnectorType:
    name: str
    payload_formats: list[str] = field(default_factory=list)
    auth_kinds: list[str] = field(default_factory=list)
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "payload_formats": list(self.payload_formats or []),
            "auth_kinds": list(self.auth_kinds or []),
            "description": self.description,
        }


@dataclass
class OnboardingRecord:
    source_id: str
    status: str
    owner: Optional[str] = None
    contact: Optional[str] = None
    go_live_date: Optional[date] = None
    escalation: Optional[str] = None
    # The connector contract (096 → 099): everything needed to RUN + govern the
    # source, not just track its lifecycle.
    config: dict = field(default_factory=dict)
    field_mappings: list = field(default_factory=list)
    record_type: Optional[str] = None
    trust_tier: Optional[int] = None
    must_capture: list[str] = field(default_factory=list)
    license: Optional[str] = None
    cadence: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "owner": self.owner,
            "contact": self.contact,
            "go_live_date": self.go_live_date.isoformat() if self.go_live_date else None,
            "escalation": self.escalation,
            "config": dict(self.config or {}),
            "field_mappings": list(self.field_mappings or []),
            "record_type": self.record_type,
            "trust_tier": self.trust_tier,
            "must_capture": list(self.must_capture or []),
            "license": self.license,
            "cadence": self.cadence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def _row_to_connector_type(row: dict) -> ConnectorType:
    return ConnectorType(
        name=row["name"],
        payload_formats=list(row.get("payload_formats") or []),
        auth_kinds=list(row.get("auth_kinds") or []),
        description=row.get("description"),
    )


def _row_to_onboarding(row: dict) -> OnboardingRecord:
    # Tolerant of rows that predate the 099 contract columns (e.g. a bare
    # start_onboarding RETURNING) — the new fields default empty/None.
    return OnboardingRecord(
        source_id=row["source_id"],
        status=row["status"],
        owner=row.get("owner"),
        contact=row.get("contact"),
        go_live_date=row.get("go_live_date"),
        escalation=row.get("escalation"),
        config=row.get("config") or {},
        field_mappings=row.get("field_mappings") or [],
        record_type=row.get("record_type"),
        trust_tier=row.get("trust_tier"),
        must_capture=list(row.get("must_capture") or []),
        license=row.get("license"),
        cadence=row.get("cadence"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ────────────────────────────────────────────────────────────────────
# Taxonomy queries
# ────────────────────────────────────────────────────────────────────

def list_connector_types(db) -> list[ConnectorType]:
    rows = db.fetch_all(
        "SELECT name, payload_formats, auth_kinds, description "
        "FROM connector_types ORDER BY name"
    )
    return [_row_to_connector_type(r) for r in (rows or [])]


def get_connector_type(db, name: str) -> Optional[ConnectorType]:
    row = db.fetch_one(
        "SELECT name, payload_formats, auth_kinds, description "
        "FROM connector_types WHERE name = %s",
        (name,),
    )
    return _row_to_connector_type(row) if row else None


def _require_connector_type(db, name: str) -> None:
    if get_connector_type(db, name) is None:
        raise UnknownConnectorType(
            f"connector_type {name!r} is not in the taxonomy "
            f"(known: {list(CONNECTOR_TYPE_NAMES)})"
        )


def set_source_connector_type(db, source_id: str, connector_type: str) -> None:
    """Assign a connector_type to an existing source. Validates against the
    taxonomy first (the DB FK is the floor; this gives a clear error early)."""
    _require_connector_type(db, connector_type)
    db.execute(
        "UPDATE sources SET connector_type = %s WHERE source_id = %s",
        (connector_type, source_id),
    )


# ────────────────────────────────────────────────────────────────────
# Onboarding lifecycle
# ────────────────────────────────────────────────────────────────────

def get_onboarding(db, source_id: str) -> Optional[OnboardingRecord]:
    row = db.fetch_one(
        f"SELECT {_ONBOARDING_COLS} FROM source_onboarding WHERE source_id = %s",
        (source_id,),
    )
    return _row_to_onboarding(row) if row else None


def start_onboarding(
    db,
    source_id: str,
    *,
    owner: Optional[str] = None,
    contact: Optional[str] = None,
    connector_type: Optional[str] = None,
    go_live_date: Optional[date] = None,
    escalation: Optional[str] = None,
) -> OnboardingRecord:
    """Begin (or return existing) onboarding for a source, in `draft`.

    Idempotent: if an onboarding row already exists it is returned unchanged
    (use `advance_onboarding` to move it). If `connector_type` is given it is
    validated and written onto the source row in the same call.
    """
    if connector_type is not None:
        _require_connector_type(db, connector_type)

    existing = get_onboarding(db, source_id)
    if existing is not None:
        # Still honour a late-supplied connector_type without resetting status.
        if connector_type is not None:
            set_source_connector_type(db, source_id, connector_type)
        return existing

    if connector_type is not None:
        set_source_connector_type(db, source_id, connector_type)

    row = db.fetch_one(
        """
        INSERT INTO source_onboarding
            (source_id, status, owner, contact, go_live_date, escalation)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING source_id, status, owner, contact, go_live_date, escalation,
                  created_at, updated_at
        """,
        (source_id, INITIAL_STATUS, owner, contact, go_live_date, escalation),
    )
    if not row:
        raise RuntimeError("start_onboarding: insert returned no row")
    return _row_to_onboarding(row)


def advance_onboarding(db, source_id: str, to_status: str) -> OnboardingRecord:
    """Move a source's onboarding to `to_status`, enforcing the state machine.

    Raises OnboardingNotFound if onboarding was never started, InvalidTransition
    if the move is illegal. A no-op (already in `to_status`) returns the current
    record unchanged rather than erroring.
    """
    current = get_onboarding(db, source_id)
    if current is None:
        raise OnboardingNotFound(f"no onboarding row for source {source_id!r}")
    if current.status == to_status:
        return current

    validate_transition(current.status, to_status)

    row = db.fetch_one(
        """
        UPDATE source_onboarding SET status = %s
        WHERE source_id = %s
        RETURNING source_id, status, owner, contact, go_live_date, escalation,
                  created_at, updated_at
        """,
        (to_status, source_id),
    )
    if not row:
        raise RuntimeError("advance_onboarding: update returned no row")
    logger.info("onboarding %s: %s → %s", source_id, current.status, to_status)
    return _row_to_onboarding(row)


def list_onboarding(db, *, status: Optional[str] = None) -> list[OnboardingRecord]:
    if status is not None and status not in ONBOARDING_STATUSES:
        raise ValueError(f"status must be one of {list(ONBOARDING_STATUSES)}")
    where = ""
    params: list[Any] = []
    if status is not None:
        where = "WHERE status = %s"
        params.append(status)
    rows = db.fetch_all(
        f"SELECT {_ONBOARDING_COLS} FROM source_onboarding {where} "
        "ORDER BY updated_at DESC",
        tuple(params) if params else None,
    )
    return [_row_to_onboarding(r) for r in (rows or [])]


# ────────────────────────────────────────────────────────────────────
# Contract persistence (099) + runnable-source query (the scheduler reads this)
# ────────────────────────────────────────────────────────────────────

def set_onboarding_contract(
    db,
    source_id: str,
    *,
    record_type: Optional[str] = None,
    config: Optional[dict] = None,
    field_mappings: Optional[list] = None,
    trust_tier: Optional[int] = None,
    must_capture: Optional[list[str]] = None,
    license: Optional[str] = None,
    cadence: Optional[dict] = None,
) -> Optional[OnboardingRecord]:
    """Persist (a subset of) the connector contract onto an existing onboarding
    row. Only the fields you pass are written, so this is safe to call repeatedly
    (e.g. the agent refining a draft). Returns the refreshed record."""
    sets: list[str] = []
    params: list[Any] = []
    if record_type is not None:
        sets.append("record_type = %s"); params.append(record_type)
    if config is not None:
        sets.append("config = %s::jsonb"); params.append(json.dumps(config))
    if field_mappings is not None:
        sets.append("field_mappings = %s::jsonb"); params.append(json.dumps(field_mappings))
    if trust_tier is not None:
        sets.append("trust_tier = %s"); params.append(trust_tier)
    if must_capture is not None:
        sets.append("must_capture = %s"); params.append(list(must_capture))
    if license is not None:
        sets.append("license = %s"); params.append(license)
    if cadence is not None:
        sets.append("cadence = %s::jsonb"); params.append(json.dumps(cadence))
    if not sets:
        return get_onboarding(db, source_id)
    params.append(source_id)
    db.execute(
        f"UPDATE source_onboarding SET {', '.join(sets)} WHERE source_id = %s",
        tuple(params),
    )
    return get_onboarding(db, source_id)


def register_contract(
    db,
    source_id: str,
    *,
    source_name: str,
    connector_type: str,
    record_type: str,
    config: Optional[dict] = None,
    field_mappings: Optional[list] = None,
    trust_tier: Optional[int] = None,
    must_capture: Optional[list[str]] = None,
    license: Optional[str] = None,
    cadence: Optional[dict] = None,
    base_url: Optional[str] = None,
    owner: Optional[str] = None,
    contact: Optional[str] = None,
) -> OnboardingRecord:
    """All-in-one: upsert the `sources` row + start onboarding (draft) + persist
    the full connector contract, idempotently. The *runnable* projection of a
    connectors/specs/<id>.yaml spec. Validate the spec (ConnectorSpec.lint) BEFORE
    calling this — kept import-free of connectors/ here to avoid a cycle."""
    from services.source_registry import SourceRegistryService

    _require_connector_type(db, connector_type)
    SourceRegistryService.register(
        db,
        source_id=source_id,
        display_name=source_name,
        tier=trust_tier or 3,
        base_url=base_url,
    )
    start_onboarding(db, source_id, owner=owner, contact=contact,
                     connector_type=connector_type)
    rec = set_onboarding_contract(
        db, source_id,
        record_type=record_type, config=config, field_mappings=field_mappings,
        trust_tier=trust_tier, must_capture=must_capture, license=license,
        cadence=cadence,
    )
    if rec is None:
        raise RuntimeError("register_contract: onboarding row missing after upsert")
    return rec


def list_runnable_sources(db) -> list[dict]:
    """Sources promoted to `prod` with a runtime connector type, plus everything
    needed to rebuild a ConnectorSpec and schedule it. The scheduler's dynamic
    pass consumes this. Returns plain dicts (no connectors/ import here → no
    import cycle; the caller builds the ConnectorSpec)."""
    rows = db.fetch_all(
        """
        SELECT o.source_id,
               s.display_name   AS source_name,
               s.connector_type AS connector_type,
               o.record_type, o.config, o.cadence, o.trust_tier
        FROM source_onboarding o
        JOIN sources s ON s.source_id = o.source_id
        WHERE o.status = 'prod'
          AND s.connector_type = ANY(%s)
          AND (s.active IS TRUE OR s.active IS NULL)
        ORDER BY o.source_id
        """,
        (list(RUNTIME_CONNECTOR_TYPES),),
    )
    return [dict(r) for r in (rows or [])]
