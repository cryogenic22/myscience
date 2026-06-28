"""ConnectorSpec — the file-based connector primitive ("Connector Press").

A connector is a plain YAML spec file (``connectors/specs/<source_id>.yaml``)
governed by ``connectors/specs/SCHEMA.md``. The spec carries the declarative
connector config (``RestConfig`` / ``CsvConfig`` / ``RssConfig``-shaped) plus the
data contract (``record_type``, ``trust_tier``, ``must_capture``, ``license``,
``cadence``). This module loads / lints a spec and — the keystone —
``build_connector_from_spec()`` turns it into ONE OF THE EXISTING generic
connectors (no new connector class). Because those connectors already emit the
universal ``RawRecord``, a source registered purely from a spec flows through the
same ``IntegrationPipeline`` (resolve → cross-link → FAIR → quality) as every
bespoke connector.

Design inspiration: Karpathy's LLM-wiki (a folder of plain files governed by one
schema, with ``load``/``lint`` ops) + Printing Press (the agent's deliverable is
a declarative connector artifact produced from a description or a probed sample).
The spec FILE owns the connector *definition* (git-tracked, agent-authored); the
DB owns *runtime state* (lifecycle, etl_runs, FAIR history).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from connectors.base import BaseConnector, RecordType
from connectors.csv_connector import CsvConfig, CsvConnector
from connectors.rest_connector import RestConfig, RestConnector
from connectors.rss_connector import RssConfig, RssConnector
from services.connector_taxonomy import CONNECTOR_TYPE_NAMES


class SpecError(ValueError):
    """A connector spec is malformed or cannot be turned into a runnable connector."""


# Taxonomy name → (config dataclass, connector class). Only these three have a
# Phase-1 runtime connector; WEB_SCRAPE / WAREHOUSE / MANUAL are valid taxonomy
# types that persist + draft fine but do not auto-run yet (a later phase).
_RUNTIME: dict[str, tuple[type, type]] = {
    "API_REST": (RestConfig, RestConnector),
    "CSV_FILE": (CsvConfig, CsvConnector),
    "RSS": (RssConfig, RssConnector),
}

_RECORD_TYPES = {rt.value for rt in RecordType}


@dataclass
class ConnectorSpec:
    """The declarative definition of one onboarded source."""

    source_id: str
    source_name: str
    connector_type: str  # one of CONNECTOR_TYPE_NAMES (API_REST | CSV_FILE | RSS | …)
    record_type: str  # a core RecordType value (drug | company | trial | …)
    config: dict[str, Any] = field(default_factory=dict)
    trust_tier: Optional[int] = None  # data-contract trust tier 1|2|3
    must_capture: list[str] = field(default_factory=list)
    license: Optional[str] = None
    cadence: Optional[dict[str, Any]] = None  # APScheduler CronTrigger kwargs; None ⇒ default

    # ── (de)serialise ──────────────────────────────────────────────
    @classmethod
    def from_dict(cls, d: dict) -> "ConnectorSpec":
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise SpecError(f"unknown spec keys: {sorted(unknown)}")
        return cls(
            source_id=d.get("source_id", ""),
            source_name=d.get("source_name", ""),
            connector_type=d.get("connector_type", ""),
            record_type=d.get("record_type", ""),
            config=dict(d.get("config") or {}),
            trust_tier=d.get("trust_tier"),
            must_capture=list(d.get("must_capture") or []),
            license=d.get("license"),
            cadence=d.get("cadence"),
        )

    @classmethod
    def from_yaml(cls, text: str) -> "ConnectorSpec":
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise SpecError("spec YAML must be a mapping")
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: "str | Path") -> "ConnectorSpec":
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "connector_type": self.connector_type,
            "record_type": self.record_type,
            "config": dict(self.config),
        }
        if self.trust_tier is not None:
            out["trust_tier"] = self.trust_tier
        if self.must_capture:
            out["must_capture"] = list(self.must_capture)
        if self.license is not None:
            out["license"] = self.license
        if self.cadence is not None:
            out["cadence"] = dict(self.cadence)
        return out

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    # ── validation (the `lint` op) ─────────────────────────────────
    def lint(self) -> list[str]:
        """Return a list of human-readable problems; empty ⇒ valid."""
        issues: list[str] = []
        if not (self.source_id or "").strip():
            issues.append("source_id is required")
        if not (self.source_name or "").strip():
            issues.append("source_name is required")
        if self.connector_type not in CONNECTOR_TYPE_NAMES:
            issues.append(
                f"connector_type '{self.connector_type}' is not a known type "
                f"({', '.join(CONNECTOR_TYPE_NAMES)})"
            )
        if self.record_type not in _RECORD_TYPES:
            issues.append(f"record_type '{self.record_type}' is not a core entity type")
        if self.trust_tier is not None and self.trust_tier not in (1, 2, 3):
            issues.append("trust_tier must be 1, 2 or 3")
        if not isinstance(self.must_capture, list):
            issues.append("must_capture must be a list of field names")
        # For runtime types, the config must actually build a valid connector
        # config (this catches a missing url / external_id_field via the
        # dataclass __post_init__).
        if self.connector_type in _RUNTIME and self.record_type in _RECORD_TYPES:
            try:
                self.to_config()
            except SpecError as e:
                issues.append(str(e))
            except Exception as e:  # ConnectorError from a config __post_init__
                issues.append(f"config invalid: {e}")
        return issues

    # ── the dynamic-loader bridge ──────────────────────────────────
    def to_config(self):
        """Build the matching generic connector config (RestConfig/CsvConfig/RssConfig)."""
        if self.connector_type not in _RUNTIME:
            raise SpecError(
                f"connector_type '{self.connector_type}' has no runtime connector "
                f"(supported: {', '.join(sorted(_RUNTIME))})"
            )
        if self.record_type not in _RECORD_TYPES:
            raise SpecError(f"record_type '{self.record_type}' is not a core entity type")
        config_cls = _RUNTIME[self.connector_type][0]
        valid = {f.name for f in dataclasses.fields(config_cls)}
        kwargs = {k: v for k, v in (self.config or {}).items() if k in valid}
        kwargs["source_id"] = self.source_id
        kwargs["source_name"] = self.source_name
        kwargs["record_type"] = RecordType(self.record_type)
        return config_cls(**kwargs)


def build_connector_from_spec(spec: ConnectorSpec) -> BaseConnector:
    """Instantiate the right EXISTING generic connector from a spec.

    This is the dynamic loader that closes the "register → it just runs" gap:
    no new connector class — Rest/Csv/Rss already emit the universal RawRecord,
    so the source flows through IntegrationPipeline unchanged.
    """
    if spec.connector_type not in _RUNTIME:
        raise SpecError(
            f"connector_type '{spec.connector_type}' has no runtime connector "
            f"(supported: {', '.join(sorted(_RUNTIME))})"
        )
    connector_cls = _RUNTIME[spec.connector_type][1]
    return connector_cls(spec.to_config())
