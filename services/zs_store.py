"""File-backed JSON store for the editable ZS Future State capability cards.

The standalone, password-gated `/zs` deck (``static/zs/zs-future-state-v2.jsx``)
ships with a baked-in ``LIBRARY`` of six capability cards. This module turns that
set into an EDITABLE, PERSISTENT collection backed by a single JSON file — no
database, no migration. It is the single source of truth for the seed: the same
six cards (and their moat scores) that the .jsx defaults to live here, so an
empty data dir hydrates to the canonical deck.

Persistence:
  * The card set is stored as one JSON file at ``ZS_DATA_DIR/capability_cards.json``.
  * ``ZS_DATA_DIR`` resolves (in order) to env ``ZS_DATA_DIR``, env
    ``RAILWAY_VOLUME_MOUNT_PATH`` (so attaching a Railway Volume makes edits
    durable with no DB), else ``<repo_root>/static/zs/data``.
  * On first read, if the file is absent it is SEEDED from ``DEFAULT_CARDS``.
  * Writes are atomic (temp file + ``os.replace``) and serialised behind a
    module-level lock so concurrent FastAPI requests can't interleave a write.

Validation lives in :class:`CapabilityCard` (services use it). ``pool`` must be a
key of :data:`POOLS` and ``model`` a key of :data:`MODELS`; unknown values raise
``ValidationError`` (the route maps that to HTTP 422).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# --- valid enum surfaces (mirror the .jsx POOLS / MODELS dicts) ------------
# Keep these in sync with static/zs/zs-future-state-v2.jsx. They are the only
# accepted values for a card's `pool` / `model`.
POOLS: tuple[str, ...] = ("ai", "rnd", "commercial", "opmodel", "mna", "governance")
MODELS: tuple[str, ...] = ("hybrid", "perunit", "gainshare", "bot", "subusage", "assurance")

# --- canonical seed: the six LIBRARY cards + their OFFERING_MOATS ----------
# Single source of truth on the server. Ported 1:1 from the .jsx so an empty
# data dir hydrates to exactly the deck's default portfolio.
DEFAULT_CARDS: list[dict[str, Any]] = [
    {
        "id": "decisionops",
        "name": "DecisionOps managed services",
        "pool": "commercial",
        "model": "hybrid",
        "size": 0.78,
        "start": 2,
        "attain": 62,
        "color": "var(--s1)",
        "buyer": "CCO · CDIO",
        "moat": "Highest — governed decision systems run as a service",
        "rationale": "World-④ product. The Decision Flywheel made into a recurring, outcome-priced business.",
        "moats": {"ground": 3, "compliance": 2, "switching": 3, "trust": 2, "convenience": 2},
    },
    {
        "id": "devreg",
        "name": "Development & Regulatory AI",
        "pool": "rnd",
        "model": "perunit",
        "size": 0.58,
        "start": 2,
        "attain": 48,
        "color": "var(--s2)",
        "buyer": "CMO · Head of Reg/Dev",
        "moat": "Governed authoring & regulatory credibility",
        "rationale": "Biggest white space and biggest value pool — but lowest right-to-win. The reSCape / DocAce lineage; most M&A goes here.",
        "moats": {"ground": 3, "compliance": 3, "switching": 2, "trust": 3, "convenience": 1},
    },
    {
        "id": "cognitive",
        "name": "Cognitive-enterprise build-operate-transfer",
        "pool": "opmodel",
        "model": "bot",
        "size": 0.45,
        "start": 1,
        "attain": 78,
        "color": "var(--s3)",
        "buyer": "CDIO · COO",
        "moat": "Medium — operating model & reference architecture",
        "rationale": "Front-loaded bridge revenue that funds the transition. Convert transfer into operate.",
        "moats": {"ground": 1, "compliance": 2, "switching": 2, "trust": 1, "convenience": 2},
    },
    {
        "id": "platform",
        "name": "Platform & data substrate (ZAIDYN)",
        "pool": "ai",
        "model": "subusage",
        "size": 0.35,
        "start": 1,
        "attain": 66,
        "color": "var(--s4)",
        "buyer": "CDIO",
        "moat": "Medium — orchestration kept proprietary",
        "rationale": "New recurring revenue; the hedge. Keep orchestration & metering yours, not a platform feature.",
        "moats": {"ground": 2, "compliance": 2, "switching": 2, "trust": 1, "convenience": 3},
    },
    {
        "id": "trust",
        "name": "Trust, governance & verification",
        "pool": "governance",
        "model": "assurance",
        "size": 0.25,
        "start": 3,
        "attain": 55,
        "color": "var(--s5)",
        "buyer": "Quality · Reg · Chief AI Officer",
        "moat": "High — option value on GxP credibility",
        "rationale": "New pool created by the FDA credibility framework and outcome accountability.",
        "moats": {"ground": 2, "compliance": 3, "switching": 1, "trust": 3, "convenience": 1},
    },
    {
        "id": "cliff",
        "name": "Cliff & launch advisory (transformed)",
        "pool": "mna",
        "model": "gainshare",
        "size": 0.25,
        "start": 1,
        "attain": 72,
        "color": "var(--s6)",
        "buyer": "CCO · Corporate development",
        "moat": "Medium-high — launch excellence on outcomes",
        "rationale": "Rides the largest near-term demand event. Episodic but high-value.",
        "moats": {"ground": 1, "compliance": 1, "switching": 1, "trust": 2, "convenience": 1},
    },
]

_DATA_FILENAME = "capability_cards.json"
_REPO_ROOT = Path(__file__).resolve().parents[1]
# Upper bound on an import payload. The deck is a curated portfolio, not a bulk
# store; this caps an (auth-gated) internet-facing write so a runaway/abusive
# import can't write an unbounded file. ~80x the six-card seed.
_MAX_IMPORT_CARDS = 500
# Serialises reads-that-seed and all writes. FastAPI may run handlers
# concurrently (threadpool for sync defs); the file write must be atomic AND
# the read-modify-write under list/create/update/delete must not interleave.
_LOCK = threading.RLock()


# --- models ----------------------------------------------------------------
class MoatScores(BaseModel):
    """Per-card moat scores, each on a 0..3 scale (mirrors OFFERING_MOATS)."""

    model_config = {"extra": "forbid"}

    ground: int = Field(default=0, ge=0, le=3)
    compliance: int = Field(default=0, ge=0, le=3)
    switching: int = Field(default=0, ge=0, le=3)
    trust: int = Field(default=0, ge=0, le=3)
    convenience: int = Field(default=0, ge=0, le=3)


class CapabilityCard(BaseModel):
    """One editable capability area. Shape mirrors a LIBRARY offering object.

    ``pool`` must be one of :data:`POOLS`; ``model`` one of :data:`MODELS`.
    ``id`` is optional on create (the store slugs one from ``name`` if absent).
    """

    model_config = {"extra": "forbid"}

    id: str | None = None
    name: str = Field(min_length=1)
    pool: str
    model: str
    size: float = Field(ge=0.0, le=1.0)
    start: int = Field(ge=1, le=20)
    attain: int = Field(ge=0, le=100)
    color: str = "var(--s1)"
    buyer: str = ""
    moat: str = ""
    rationale: str = ""
    moats: MoatScores = Field(default_factory=MoatScores)

    @field_validator("pool")
    @classmethod
    def _check_pool(cls, v: str) -> str:
        if v not in POOLS:
            raise ValueError(f"pool must be one of {POOLS}, got {v!r}")
        return v

    @field_validator("model")
    @classmethod
    def _check_model(cls, v: str) -> str:
        if v not in MODELS:
            raise ValueError(f"model must be one of {MODELS}, got {v!r}")
        return v


def _slugify(name: str) -> str:
    """Lower-case alnum slug from a name; falls back to 'card' if empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "card"


# --- store ------------------------------------------------------------------
def data_dir() -> Path:
    """Resolve the data directory (env override → Railway volume → repo static).

    Read at call time (not import) so tests can monkeypatch the env var.
    """
    override = os.getenv("ZS_DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if override:
        return Path(override)
    return _REPO_ROOT / "static" / "zs" / "data"


def data_file() -> Path:
    return data_dir() / _DATA_FILENAME


def _default_payload() -> dict[str, Any]:
    # Re-validate the seed through the model so the file always matches schema.
    cards = [CapabilityCard(**c).model_dump() for c in DEFAULT_CARDS]
    return {"cards": cards}


def _atomic_write(payload: dict[str, Any]) -> None:
    """Write payload to the data file atomically (temp file + os.replace)."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = data_file()
    tmp = target.with_suffix(target.suffix + f".tmp-{os.getpid()}-{threading.get_ident()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)  # atomic on POSIX and Windows


def _quarantine_corrupt(f: Path) -> Path:
    """Move a corrupt data file aside (non-clobbering) and return the backup path.

    Preserves the bad bytes for recovery rather than discarding them — so a
    re-seed is never a silent data loss.
    """
    backup = f.with_suffix(f.suffix + ".corrupt")
    n = 1
    while backup.exists():
        backup = f.with_suffix(f.suffix + f".corrupt.{n}")
        n += 1
    os.replace(f, backup)  # atomic rename, keeps the original bytes
    return backup


def _read_raw() -> dict[str, Any]:
    """Read the file, seeding it from defaults if absent. Returns the payload.

    If the file is present but unparseable or malformed (external edit, a partial
    write from another tool, disk trouble), it is quarantined — moved aside to a
    ``.corrupt`` sibling and logged — and the store re-seeds from defaults. This
    keeps the page alive (a corrupt file would otherwise 500 every request,
    including read) while never silently discarding the bad data.
    """
    with _LOCK:
        f = data_file()
        if not f.is_file():
            payload = _default_payload()
            _atomic_write(payload)
            return payload
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
                raise ValueError("expected {'cards': [...]}")
        except (json.JSONDecodeError, ValueError) as exc:
            backup = _quarantine_corrupt(f)
            logger.warning(
                "zs_store: %s is corrupt (%s) — quarantined to %s, re-seeding from defaults",
                f, exc, backup,
            )
            payload = _default_payload()
            _atomic_write(payload)
            return payload
        return data


def load() -> list[CapabilityCard]:
    """Return all cards (seeding the file on first access). Validated."""
    raw = _read_raw()
    return [CapabilityCard(**c) for c in raw["cards"]]


def export_dict() -> dict[str, Any]:
    """Return the full, validated card set as a plain dict (for download)."""
    return {"cards": [c.model_dump() for c in load()]}


def _save(cards: list[CapabilityCard]) -> None:
    _atomic_write({"cards": [c.model_dump() for c in cards]})


def get(card_id: str) -> CapabilityCard | None:
    return next((c for c in load() if c.id == card_id), None)


def create(card: CapabilityCard) -> CapabilityCard:
    """Add a card. Assigns a slug id if absent. Rejects duplicate ids."""
    with _LOCK:
        cards = load()
        existing_ids = {c.id for c in cards}
        new_id = card.id or _slugify(card.name)
        if new_id in existing_ids:
            raise ValueError(f"card id {new_id!r} already exists")
        stored = card.model_copy(update={"id": new_id})
        cards.append(stored)
        _save(cards)
        return stored


def update(card_id: str, card: CapabilityCard) -> CapabilityCard | None:
    """Replace the card with ``card_id``. Returns None if it doesn't exist.

    The path id wins: the stored card keeps ``card_id`` regardless of any id in
    the body (no id renames / collisions through update).
    """
    with _LOCK:
        cards = load()
        idx = next((i for i, c in enumerate(cards) if c.id == card_id), None)
        if idx is None:
            return None
        stored = card.model_copy(update={"id": card_id})
        cards[idx] = stored
        _save(cards)
        return stored


def delete(card_id: str) -> bool:
    """Remove the card. Returns True if one was removed, False if not found."""
    with _LOCK:
        cards = load()
        kept = [c for c in cards if c.id != card_id]
        if len(kept) == len(cards):
            return False
        _save(kept)
        return True


def replace_all(payload: dict[str, Any]) -> list[CapabilityCard]:
    """Validate and replace the entire set from a posted dict (import).

    Each card is validated; ids are assigned by slug where absent and must be
    unique. Raises ValueError on a malformed payload or duplicate ids; the
    on-disk file is only overwritten once the whole set validates.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        raise ValueError("import payload must be an object with a 'cards' list")
    if len(payload["cards"]) > _MAX_IMPORT_CARDS:
        raise ValueError(
            f"import exceeds the {_MAX_IMPORT_CARDS}-card limit "
            f"({len(payload['cards'])} cards)"
        )
    validated: list[CapabilityCard] = []
    seen: set[str] = set()
    for raw in payload["cards"]:
        card = CapabilityCard(**raw)  # raises ValidationError on bad pool/model/etc.
        cid = card.id or _slugify(card.name)
        if cid in seen:
            raise ValueError(f"duplicate card id in import: {cid!r}")
        seen.add(cid)
        validated.append(card.model_copy(update={"id": cid}))
    with _LOCK:
        _save(validated)
    return validated
