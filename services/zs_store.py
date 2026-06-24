"""File-backed JSON store for the editable ZS Future State card families.

The standalone, password-gated `/zs` deck (``static/zs/zs-future-state-v2.jsx``)
ships with baked-in defaults for three editable card *families*:

  * ``cards``      — capability areas / offerings (the original family)
  * ``constructs`` — commercial constructs (how ZS charges)
  * ``bets``       — capability bets (where ZS places big chips)

This module turns each set into an EDITABLE, PERSISTENT collection backed by a
single JSON file per family — no database, no migration. It is the single source
of truth for each seed: the same defaults the .jsx falls back to live here, so an
empty data dir hydrates to the canonical deck.

Persistence:
  * Each family is stored as one JSON file at ``ZS_DATA_DIR/<filename>`` —
    ``capability_cards.json``, ``commercial_constructs.json``,
    ``capability_bets.json``.
  * ``ZS_DATA_DIR`` resolves (in order) to env ``ZS_DATA_DIR``, env
    ``RAILWAY_VOLUME_MOUNT_PATH`` (so attaching a Railway Volume makes edits
    durable with no DB), else ``<repo_root>/static/zs/data``.
  * On first read, if a family's file is absent it is SEEDED from its defaults.
  * Writes are atomic (temp file + ``os.replace``) and serialised behind a
    module-level lock so concurrent FastAPI requests can't interleave a write.
  * A corrupt/malformed file is quarantined (bytes preserved) and re-seeded —
    this applies to ALL families (shared code path), so a read never 500s.
  * Imports are bounded by :data:`_MAX_IMPORT_CARDS` for every family.

Every PUBLIC function takes ``family: str = "cards"`` so the original callers
(and the original tests) keep working unchanged while the two new families ride
the identical machinery.

Validation lives in the per-family Pydantic models. Unknown enum values raise
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
# accepted values for a capability card's `pool` / `model`.
POOLS: tuple[str, ...] = ("ai", "rnd", "commercial", "opmodel", "mna", "governance")
MODELS: tuple[str, ...] = ("hybrid", "perunit", "gainshare", "bot", "subusage", "assurance")

# Enum surfaces for the two new families (mirror the .jsx selects). Each is
# OPTIONAL on its card — an empty string means "unset" and is always allowed.
CONSTRUCT_QUALITIES: tuple[str, ...] = ("recurring", "outcome", "project")
BET_HORIZONS: tuple[str, ...] = ("near", "mid", "moonshot")
BET_POSTURES: tuple[str, ...] = ("build", "partner", "consume")

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

# --- canonical seed: commercial constructs (how ZS charges) ----------------
# Ported 1:1 from the strategy substance — do not paraphrase.
DEFAULT_CONSTRUCTS: list[dict[str, Any]] = [
    {
        "id": "floor-per-hit",
        "name": "Floor + per-hit",
        "meter": "A discrete, pre-agreed outcome event ('a hit')",
        "value_story": "A fixed base retainer covers ZS's delivery-cost floor and de-risks procurement; a success fee fires per realized outcome event.",
        "quality": "outcome",
        "buyer": "CFO / procurement + the business owner",
        "zs_risk": "Defining the 'hit' tight enough to be attributable yet loose enough to fire often.",
        "fit": "Needs a clean, discrete, attributable event.",
        "examples": "First-cycle FDA acceptance · formulary add · launch month-6 inside a trajectory band · a field action that clears a pre-agreed threshold",
    },
    {
        "id": "decision-latency-sla",
        "name": "Decision-latency SLA",
        "meter": "Time from data-capture → decision, against a guaranteed SLA",
        "value_story": "You don't sell the model — you sell the weeks of spend reallocated earlier. 'Allocation-ready answer in N days or you don't pay the premium.' A platform structurally can't sell this; ZS can because ZS runs it.",
        "quality": "recurring",
        "buyer": "Brand / commercial lead",
        "zs_risk": "Owning the data plumbing end-to-end to actually hit the SLA.",
        "fit": "A slow, repeated decision cycle you can compress and own.",
        "examples": "Marketing-mix cycle 3 months → 4 weeks · brand-plan reallocation · trial-enrollment decision compression",
    },
    {
        "id": "gain-share",
        "name": "Gain-share / outcome",
        "meter": "A share of measured lift",
        "value_story": "Only where attribution is clean. Build holdout/geo-experiment design into delivery so you become the agreed scorekeeper — itself a moat.",
        "quality": "outcome",
        "buyer": "Commercial / market access",
        "zs_risk": "Confounding — the drug's success isn't all your intervention.",
        "fit": "Clean attribution plus a metering/measurement layer.",
        "examples": "Access pull-through (formulary → script lift) · launch vs. analog benchmark · incremental Rx from next-best-action",
    },
    {
        "id": "cost-to-serve-takeout",
        "name": "Cost-to-serve takeout",
        "meter": "% below the client's insourced/GCC cost + an operate retainer",
        "value_story": "Price against the fully-loaded cost they avoid, with governance they can't staff. Makes the operate tail the product (fights BOT transfer leakage).",
        "quality": "project",
        "buyer": "COO / CDIO",
        "zs_risk": "Margin compression if the takeout % is too aggressive.",
        "fit": "Where the client's alternative is a GCC / insourcing.",
        "examples": "MLR review throughput · medical-information ops · analytics run",
    },
    {
        "id": "assurance-per-cert",
        "name": "Assurance / per-cert",
        "meter": "Per validated decision / certified model / audit-ready artifact",
        "value_story": "Sell credibility as a line item. Near-zero marginal cost on the Nth certification through a governed harness.",
        "quality": "recurring",
        "buyer": "Quality · Regulatory · Chief AI Officer",
        "zs_risk": "Liability if a certified output is later challenged.",
        "fit": "Regulated outputs under the FDA credibility framework.",
        "examples": "Per-ePI · per-submission · per-model-validation",
    },
    {
        "id": "outcome-underwriting",
        "name": "Outcome underwriting (frontier)",
        "meter": "A guaranteed floor + shared upside on a decision outcome",
        "value_story": "The purest 'outcome operator' — you take a position. Requires balance-sheet capacity + actuarial data (the flywheel).",
        "quality": "outcome",
        "buyer": "CCO / corporate development",
        "zs_risk": "Can't run on a billable-hour P&L; gated on the flywheel-ownership question.",
        "fit": "Year 3-5, only once cross-client ground-truth is contractually real.",
        "examples": "Launch outcome guarantee · access-win guarantee",
    },
]

# --- canonical seed: capability bets (where ZS places big chips) -----------
# Ported 1:1 from the strategy substance — do not paraphrase.
DEFAULT_BETS: list[dict[str, Any]] = [
    {
        "id": "simulation-aas",
        "name": "Decision Simulation-as-a-Service",
        "thesis": "Run the decision before you make it — launch/payer/allocation/portfolio sims. ZS is already building the simulator (the v2 instrument), and it compounds the flywheel.",
        "unit_moat": "Per-simulation / subscription; moat = calibration data (your decision ground-truth makes your sims more right than a generic one).",
        "kill_criterion": "If the sims aren't demonstrably better-calibrated than generic or the client's own → it's Monte-Carlo theater.",
        "ceiling": "$1B",
        "horizon": "near",
        "posture": "build",
        "native": True,
    },
    {
        "id": "digital-twin",
        "name": "Digital Twin",
        "thesis": "A living, governed twin of an asset / market / patient population / trial that you keep in sync and run scenarios against — pure 'translation' craft.",
        "unit_moat": "Subscription per twin + usage; the twin is the substrate, simulation is the verb on it.",
        "kill_criterion": "RWD / data rights — IQVIA owns much of the underlying data; partner or contest.",
        "ceiling": "$1B",
        "horizon": "mid",
        "posture": "build",
        "native": True,
    },
    {
        "id": "pharma-slms",
        "name": "Pharma SLMs",
        "thesis": "Don't build frontier (rent it). Own small, governable, domain-tuned models for narrow regulated tasks (ePI, CRL, MLR), tuned on your decision corpus. Instantiates rent-frontier / own-the-orchestration.",
        "unit_moat": "Embedded in the service-as-software units or licensed on-prem; moat = the training corpus + the eval harness that proves them.",
        "kill_criterion": "Frontier models get cheap + governable enough to erase the edge — keep it a thin layer.",
        "ceiling": "$0.5–1B",
        "horizon": "mid",
        "posture": "build",
        "native": True,
    },
    {
        "id": "the-harness",
        "name": "The Harness (governance standard)",
        "thesis": "The eval/governance/orchestration layer is the moat the strategy says to own. Make it the de-facto standard FDA-credibility runs through → a tollbooth on every governed pharma AI decision, including competitors'. The sleeper bet.",
        "unit_moat": "Subscription + per-certification; standards-ownership is winner-take-most.",
        "kill_criterion": "A hyperscaler or IQVIA sets the standard first, or FDA blesses someone else's framework.",
        "ceiling": "$1B+",
        "horizon": "moonshot",
        "posture": "build",
        "native": True,
    },
    {
        "id": "quantum",
        "name": "Quantum",
        "thesis": "Almost certainly NOT ZS to build — ZS would be the application/translation layer on someone else's quantum (rent the intelligence again).",
        "unit_moat": "A research partnership + a small option stake, not a revenue line.",
        "kill_criterion": "Don't let a buzzword become a budget line — the right posture is an option, not a line.",
        "ceiling": "Speculative",
        "horizon": "moonshot",
        "posture": "partner",
        "native": False,
    },
    {
        "id": "hardware-edge",
        "name": "Hardware / edge",
        "thesis": "Weakest fit — capital-heavy, low-margin, far from the craft. The only angle: a governed decision appliance inside a pharma firewall for sensitive SLM inference — and partner for the metal.",
        "unit_moat": "Consume, don't build.",
        "kill_criterion": "Deprioritize as a revenue bet entirely.",
        "ceiling": "Low",
        "horizon": "moonshot",
        "posture": "consume",
        "native": False,
    },
]

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Upper bound on an import payload (per family). The deck is a curated portfolio,
# not a bulk store; this caps an (auth-gated) internet-facing write so a
# runaway/abusive import can't write an unbounded file. ~80x the six-item seed.
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


class ConstructCard(BaseModel):
    """One editable commercial construct (how ZS charges).

    Light validation: these hold prose the user edits. ``quality``, when
    non-empty, must be one of :data:`CONSTRUCT_QUALITIES`. ``id`` is optional on
    create (the store slugs one from ``name`` if absent).
    """

    model_config = {"extra": "forbid"}

    id: str | None = None
    name: str = Field(min_length=1)
    meter: str = ""
    value_story: str = ""
    quality: str = ""
    buyer: str = ""
    zs_risk: str = ""
    fit: str = ""
    examples: str = ""

    @field_validator("quality")
    @classmethod
    def _check_quality(cls, v: str) -> str:
        if v and v not in CONSTRUCT_QUALITIES:
            raise ValueError(f"quality must be one of {CONSTRUCT_QUALITIES}, got {v!r}")
        return v


class BetCard(BaseModel):
    """One editable capability bet (where ZS places big chips).

    Light validation: these hold prose the user edits. ``horizon`` / ``posture``,
    when non-empty, must be one of :data:`BET_HORIZONS` / :data:`BET_POSTURES`.
    ``id`` is optional on create (the store slugs one from ``name`` if absent).
    """

    model_config = {"extra": "forbid"}

    id: str | None = None
    name: str = Field(min_length=1)
    thesis: str = ""
    unit_moat: str = ""
    kill_criterion: str = ""
    ceiling: str = ""
    horizon: str = ""
    posture: str = ""
    native: bool = True

    @field_validator("horizon")
    @classmethod
    def _check_horizon(cls, v: str) -> str:
        if v and v not in BET_HORIZONS:
            raise ValueError(f"horizon must be one of {BET_HORIZONS}, got {v!r}")
        return v

    @field_validator("posture")
    @classmethod
    def _check_posture(cls, v: str) -> str:
        if v and v not in BET_POSTURES:
            raise ValueError(f"posture must be one of {BET_POSTURES}, got {v!r}")
        return v


# --- family registry -------------------------------------------------------
# Each family is (Pydantic model, on-disk filename, default seed). Every family
# rides the identical read/write/CRUD/self-heal/import-bound machinery below.
_FAMILIES: dict[str, tuple[type[BaseModel], str, list[dict[str, Any]]]] = {
    "cards": (CapabilityCard, "capability_cards.json", DEFAULT_CARDS),
    "constructs": (ConstructCard, "commercial_constructs.json", DEFAULT_CONSTRUCTS),
    "bets": (BetCard, "capability_bets.json", DEFAULT_BETS),
}


def families() -> tuple[str, ...]:
    """The registered card family names (``("cards", "constructs", "bets")``)."""
    return tuple(_FAMILIES)


def _family(family: str) -> tuple[type[BaseModel], str, list[dict[str, Any]]]:
    """Resolve a family name to (model, filename, seed); raise on unknown."""
    try:
        return _FAMILIES[family]
    except KeyError:
        raise ValueError(
            f"unknown card family {family!r} (expected one of {tuple(_FAMILIES)})"
        ) from None


def model_for(family: str = "cards") -> type[BaseModel]:
    """The Pydantic model class backing a family (used by the route to validate)."""
    model, _, _ = _family(family)
    return model


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


def data_file(family: str = "cards") -> Path:
    """Path to a family's JSON file in the data dir."""
    _, filename, _ = _family(family)
    return data_dir() / filename


def _default_payload(family: str) -> dict[str, Any]:
    # Re-validate the seed through the model so the file always matches schema.
    model, _, seed = _family(family)
    cards = [model(**c).model_dump() for c in seed]
    return {"cards": cards}


def _atomic_write(family: str, payload: dict[str, Any]) -> None:
    """Write payload to the family's data file atomically (temp + os.replace)."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = data_file(family)
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


def _read_raw(family: str = "cards") -> dict[str, Any]:
    """Read a family's file, seeding it from defaults if absent. Returns payload.

    If the file is present but unparseable or malformed (external edit, a partial
    write from another tool, disk trouble), it is quarantined — moved aside to a
    ``.corrupt`` sibling and logged — and the store re-seeds from defaults. This
    keeps the page alive (a corrupt file would otherwise 500 every request,
    including read) while never silently discarding the bad data. The self-heal
    is shared, so it covers every family identically.
    """
    with _LOCK:
        f = data_file(family)
        if not f.is_file():
            payload = _default_payload(family)
            _atomic_write(family, payload)
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
            payload = _default_payload(family)
            _atomic_write(family, payload)
            return payload
        return data


def load(family: str = "cards") -> list[BaseModel]:
    """Return all cards in a family (seeding the file on first access). Validated."""
    model, _, _ = _family(family)
    raw = _read_raw(family)
    return [model(**c) for c in raw["cards"]]


def export_dict(family: str = "cards") -> dict[str, Any]:
    """Return the full, validated set for a family as a plain dict (for download)."""
    return {"cards": [c.model_dump() for c in load(family)]}


def _save(family: str, cards: list[BaseModel]) -> None:
    _atomic_write(family, {"cards": [c.model_dump() for c in cards]})


def get(card_id: str, family: str = "cards") -> BaseModel | None:
    return next((c for c in load(family) if c.id == card_id), None)


def create(card: BaseModel, family: str = "cards") -> BaseModel:
    """Add a card to a family. Assigns a slug id if absent. Rejects duplicate ids."""
    with _LOCK:
        cards = load(family)
        existing_ids = {c.id for c in cards}
        new_id = card.id or _slugify(card.name)
        if new_id in existing_ids:
            raise ValueError(f"card id {new_id!r} already exists")
        stored = card.model_copy(update={"id": new_id})
        cards.append(stored)
        _save(family, cards)
        return stored


def update(card_id: str, card: BaseModel, family: str = "cards") -> BaseModel | None:
    """Replace the card with ``card_id`` in a family. Returns None if absent.

    The path id wins: the stored card keeps ``card_id`` regardless of any id in
    the body (no id renames / collisions through update).
    """
    with _LOCK:
        cards = load(family)
        idx = next((i for i, c in enumerate(cards) if c.id == card_id), None)
        if idx is None:
            return None
        stored = card.model_copy(update={"id": card_id})
        cards[idx] = stored
        _save(family, cards)
        return stored


def delete(card_id: str, family: str = "cards") -> bool:
    """Remove a card from a family. Returns True if removed, False if not found."""
    with _LOCK:
        cards = load(family)
        kept = [c for c in cards if c.id != card_id]
        if len(kept) == len(cards):
            return False
        _save(family, kept)
        return True


def replace_all(payload: dict[str, Any], family: str = "cards") -> list[BaseModel]:
    """Validate and replace the entire set for a family from a posted dict (import).

    Each card is validated against the family's model; ids are assigned by slug
    where absent and must be unique. Raises ValueError on a malformed payload,
    an over-limit import, or duplicate ids; the on-disk file is only overwritten
    once the whole set validates. The import bound is shared, so it covers every
    family identically.
    """
    model, _, _ = _family(family)
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        raise ValueError("import payload must be an object with a 'cards' list")
    if len(payload["cards"]) > _MAX_IMPORT_CARDS:
        raise ValueError(
            f"import exceeds the {_MAX_IMPORT_CARDS}-card limit "
            f"({len(payload['cards'])} cards)"
        )
    validated: list[BaseModel] = []
    seen: set[str] = set()
    for raw in payload["cards"]:
        card = model(**raw)  # raises ValidationError on bad enum / shape / etc.
        cid = card.id or _slugify(card.name)
        if cid in seen:
            raise ValueError(f"duplicate card id in import: {cid!r}")
        seen.add(cid)
        validated.append(card.model_copy(update={"id": cid}))
    with _LOCK:
        _save(family, validated)
    return validated
