"""Stable contracts and side-effect-free primitives for TIV2 coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlsplit


GRAPH_SCHEMA = "market-zero-work-graph/v1"
SNAPSHOT_SCHEMA = "market-zero-controller-snapshot/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
MIGRATION_RE = re.compile(r"^[0-9]{3}$")
ACCEPTANCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]*#[1-9][0-9]*$")
MAX_SNAPSHOT_AGE = timedelta(minutes=5)
MAX_CLOCK_SKEW = timedelta(minutes=1)


@dataclass(frozen=True, order=True)
class Violation:
    """One deterministic policy failure."""

    code: str
    item_id: str
    message: str


class CoordinationViolation(ValueError):
    """Raised when the work graph or controller snapshot is unsafe."""

    def __init__(self, violations: Iterable[Violation]):
        self.violations = tuple(sorted(violations))
        detail = "; ".join(
            f"{violation.code}[{violation.item_id}]: {violation.message}"
            for violation in self.violations
        )
        super().__init__(detail)


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One canonical acceptance statement and its independent verifier."""

    id: str
    statement: str
    verification: tuple[str, ...]


@dataclass(frozen=True)
class WorkItem:
    """One immutable node in the protected work graph."""

    id: str
    title: str
    lane: str
    priority: int
    contract_status: str
    depends_on: tuple[str, ...]
    spec_path: str
    acceptance: tuple[AcceptanceCriterion, ...]
    allowed_paths: tuple[str, ...]
    denied_paths: tuple[str, ...]
    migration: str | None
    required_checks: tuple[str, ...]
    risk: str
    protected_scopes: tuple[str, ...]
    protected_decision: str | None
    protected_status: str | None

    @property
    def acceptance_ids(self) -> tuple[str, ...]:
        return tuple(criterion.id for criterion in self.acceptance)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkItem":
        spec = raw.get("spec") if isinstance(raw.get("spec"), dict) else {}
        paths = raw.get("paths") if isinstance(raw.get("paths"), dict) else {}
        protected = (
            raw.get("protected_change")
            if isinstance(raw.get("protected_change"), dict)
            else {}
        )
        raw_acceptance = (
            spec.get("acceptance")
            if isinstance(spec.get("acceptance"), dict)
            else {}
        )
        acceptance = tuple(
            AcceptanceCriterion(
                id=criterion_id,
                statement=value.get("statement", "")
                if isinstance(value, dict)
                else "",
                verification=tuple(value.get("verification", ()))
                if isinstance(value, dict)
                and isinstance(value.get("verification", ()), list)
                and all(
                    isinstance(verifier, str)
                    for verifier in value.get("verification", ())
                )
                else (),
            )
            for criterion_id, value in raw_acceptance.items()
            if isinstance(criterion_id, str)
        )
        return cls(
            id=raw.get("id", "") if isinstance(raw.get("id"), str) else "",
            title=raw.get("title", "")
            if isinstance(raw.get("title"), str)
            else "",
            lane=raw.get("lane", "")
            if isinstance(raw.get("lane"), str)
            else "",
            priority=raw.get("priority", -1),
            contract_status=raw.get("contract_status", "")
            if isinstance(raw.get("contract_status"), str)
            else "",
            depends_on=tuple(
                value for value in raw.get("depends_on", ()) if isinstance(value, str)
            )
            if isinstance(raw.get("depends_on", ()), list)
            else (),
            spec_path=spec.get("path", "")
            if isinstance(spec.get("path"), str)
            else "",
            acceptance=acceptance,
            allowed_paths=tuple(
                value for value in paths.get("allow", ()) if isinstance(value, str)
            )
            if isinstance(paths.get("allow", ()), list)
            else (),
            denied_paths=tuple(
                value for value in paths.get("deny", ()) if isinstance(value, str)
            )
            if isinstance(paths.get("deny", ()), list)
            else (),
            migration=raw.get("migration"),
            required_checks=tuple(
                value
                for value in raw.get("required_checks", ())
                if isinstance(value, str)
            )
            if isinstance(raw.get("required_checks", ()), list)
            else (),
            risk=raw.get("risk", "")
            if isinstance(raw.get("risk"), str)
            else "",
            protected_scopes=tuple(
                value
                for value in protected.get("scope", ())
                if isinstance(value, str)
            )
            if isinstance(protected.get("scope", ()), list)
            else (),
            protected_decision=protected.get("owner_decision"),
            protected_status=protected.get("status"),
        )


@dataclass(frozen=True)
class ReadinessResult:
    id: str
    ready: bool
    violations: tuple[Violation, ...]


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def strict_json_loads(value: str | bytes) -> Any:
    """Parse standards-compliant JSON and reject duplicate object keys."""

    def object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = item
        return result

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON number is forbidden: {token}")

    def finite_float(token: str) -> float:
        parsed = float(token)
        if not math.isfinite(parsed):
            raise ValueError(f"JSON number exceeds finite range: {token}")
        return parsed

    return json.loads(
        value,
        object_pairs_hook=object_from_pairs,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )


def is_int(value: Any) -> bool:
    return type(value) is int


def is_positive_int(value: Any) -> bool:
    return is_int(value) and value > 0


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_https_url(value: Any) -> bool:
    if not is_nonempty_string(value):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def is_string_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
    )


def valid_path_pattern(pattern: Any) -> bool:
    if not isinstance(pattern, str) or not pattern or "\\" in pattern:
        return False
    if pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern):
        return False
    if any(part in {"", ".", ".."} for part in pattern.split("/")):
        return False
    wildcard_count = pattern.count("*")
    return wildcard_count == 0 or (
        wildcard_count == 2 and pattern.endswith("/**")
    )


def pattern_prefix(pattern: str) -> str:
    return pattern[:-3].rstrip("/") if pattern.endswith("/**") else pattern


def matches(pattern: str, path: str) -> bool:
    prefix = pattern_prefix(pattern)
    if pattern.endswith("/**"):
        return path == prefix or path.startswith(prefix + "/")
    return path == prefix


def patterns_overlap(left: str, right: str) -> bool:
    left_prefix = pattern_prefix(left)
    right_prefix = pattern_prefix(right)
    left_tree = left.endswith("/**")
    right_tree = right.endswith("/**")
    if not left_tree and not right_tree:
        return left_prefix == right_prefix
    if left_tree and right_tree:
        return (
            left_prefix == right_prefix
            or left_prefix.startswith(right_prefix + "/")
            or right_prefix.startswith(left_prefix + "/")
        )
    if left_tree:
        return right_prefix == left_prefix or right_prefix.startswith(left_prefix + "/")
    return left_prefix == right_prefix or left_prefix.startswith(right_prefix + "/")


def load_protected_surface(path: str | Path) -> tuple[str, ...]:
    """Load the repository protection source, converting directory entries."""

    entries: list[str] = []
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        pattern = f"{entry.rstrip('/')}/**" if entry.endswith("/") else entry
        if not valid_path_pattern(pattern):
            raise ValueError(
                f"invalid protected path at {path}:{line_number}: {entry!r}"
            )
        entries.append(pattern)
    if not entries:
        raise ValueError(f"protected surface is empty: {path}")
    if len(entries) != len(set(entries)):
        raise ValueError(f"protected surface has duplicate entries: {path}")
    return tuple(entries)
