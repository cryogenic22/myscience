"""SPEC-021 D2 — numeric calibration math.

Replaces the 4-quadrant categorical heuristic from D MVP with a real
predicted-vs-actual numeric distance. Falls back to the heuristic when
parsing fails so D2 is strictly an upgrade, never a regression.

Patterns supported by `parse_target_value`:
  - "+3pp", "-2pp", "+3 pp by Q4"               → ParsedTarget(unit=pp)
  - "$5B", "$500M", "$1.2B by 2027"             → ParsedTarget(unit=usd)
  - "Phase 3 by Q3 2026"                        → ParsedTarget(unit=phase)
  - "<6 months", "<= 90 days"                   → ParsedTarget(unit=duration)
  - ">=80% adherence", ">= 80%"                 → ParsedTarget(unit=percent)
  - free-form text                              → None (caller falls back)

Numeric distance is normalized into a [0, 1] calibration score where
1.0 = bang-on prediction, 0.0 = predicted opposite/wildly-off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional


# ────────────────────────────────────────────────────────────────────
# Parsed target — structured form of free-text target_value
# ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParsedTarget:
    """Structured form of a free-text target_value string.

    `magnitude` is signed where direction matters (pp, usd) and
    positive otherwise. `unit` discriminates the comparison method.
    `by_date` is the deadline if mentioned (e.g. "by Q4 2026"); None
    means no deadline component, in which case temporal proximity
    isn't part of the comparison.
    """
    magnitude: float
    unit: str  # 'pp' | 'usd' | 'phase' | 'duration' | 'percent'
    direction: str  # 'increase' | 'decrease' | 'eq' | 'lte' | 'gte'
    by_date: Optional[date] = None
    raw: str = ""


# ────────────────────────────────────────────────────────────────────
# Parsing
# ────────────────────────────────────────────────────────────────────

# Order matters — try the most specific patterns first.

_QUARTER_RE = re.compile(r"\bq([1-4])\s*(\d{4})?", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _extract_by_date(text: str) -> Optional[date]:
    """Pull a deadline out of a target string. Returns None when none."""
    if not text:
        return None
    s = text.lower()
    m_iso = _ISO_DATE_RE.search(s)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass
    m_q = _QUARTER_RE.search(s)
    if m_q:
        q = int(m_q.group(1))
        year = int(m_q.group(2)) if m_q.group(2) else date.today().year
        end_month = q * 3
        # End of quarter (close enough — use last day of last month in Q)
        if end_month == 12:
            return date(year, 12, 31)
        # Use the last day of the month conservatively (28 to avoid leap edge cases here)
        return date(year, end_month, 28)
    m_y = _YEAR_RE.search(s)
    if m_y:
        return date(int(m_y.group(1)), 12, 31)
    return None


# pp / percentage points — "+3pp", "-2 pp", "+3pp by Q4 2026"
_PP_RE = re.compile(r"([+\-]?)\s*(\d+(?:\.\d+)?)\s*pp\b", re.IGNORECASE)

# Currency — "$5B", "$500M", "$1.2B"
_USD_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*([bm])?\b", re.IGNORECASE)

# Phase — "Phase 3", "phase 2"
_PHASE_RE = re.compile(r"phase\s*([1-4])", re.IGNORECASE)

# Duration — "<6 months", "<= 90 days", "within 12 weeks"
_DURATION_RE = re.compile(
    r"(?:(<=?|<)|within)?\s*(\d+(?:\.\d+)?)\s*(day|week|month|year)s?",
    re.IGNORECASE,
)

# Percent — "80%", ">=80% adherence"
_PERCENT_RE = re.compile(r"(>=?|<=?|>|<)?\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)


def parse_target_value(text: Optional[str]) -> Optional[ParsedTarget]:
    """Parse a free-text target_value into structured form.

    Returns None when no recognized pattern matches; caller should fall
    back to the categorical heuristic.
    """
    if not text:
        return None
    s = text.strip()
    if not s:
        return None

    by_date = _extract_by_date(s)

    # Percentage points (must precede plain percent to avoid eating "pp")
    m = _PP_RE.search(s)
    if m:
        sign = m.group(1)
        mag = float(m.group(2))
        direction = "decrease" if sign == "-" else "increase"
        signed_mag = -mag if sign == "-" else mag
        return ParsedTarget(
            magnitude=signed_mag, unit="pp", direction=direction,
            by_date=by_date, raw=s,
        )

    # Currency
    m = _USD_RE.search(s)
    if m:
        mag = float(m.group(1))
        suffix = (m.group(2) or "").upper()
        if suffix == "B":
            mag *= 1_000_000_000
        elif suffix == "M":
            mag *= 1_000_000
        return ParsedTarget(
            magnitude=mag, unit="usd", direction="eq",
            by_date=by_date, raw=s,
        )

    # Phase
    m = _PHASE_RE.search(s)
    if m:
        return ParsedTarget(
            magnitude=float(m.group(1)), unit="phase", direction="eq",
            by_date=by_date, raw=s,
        )

    # Duration
    m = _DURATION_RE.search(s)
    if m:
        op = (m.group(1) or "").lower()
        mag = float(m.group(2))
        unit_word = m.group(3).lower()
        # Normalize to days
        if unit_word.startswith("week"):
            mag *= 7
        elif unit_word.startswith("month"):
            mag *= 30
        elif unit_word.startswith("year"):
            mag *= 365
        direction = "lte" if op in ("<", "<=") else "eq"
        return ParsedTarget(
            magnitude=mag, unit="duration", direction=direction,
            by_date=by_date, raw=s,
        )

    # Percent
    m = _PERCENT_RE.search(s)
    if m:
        op = (m.group(1) or "").lower()
        mag = float(m.group(2))
        if op in (">", ">="):
            direction = "gte"
        elif op in ("<", "<="):
            direction = "lte"
        else:
            direction = "eq"
        return ParsedTarget(
            magnitude=mag, unit="percent", direction=direction,
            by_date=by_date, raw=s,
        )

    return None


# ────────────────────────────────────────────────────────────────────
# Numeric calibration scoring
# ────────────────────────────────────────────────────────────────────

# Tolerance per unit — distance below this counts as "spot on" (= 1.0).
# Distances above this decay linearly to 0.0 at 4×tolerance.
_TOLERANCE = {
    "pp": 1.0,                # 1 percentage point
    "usd": 0.10,              # 10% relative tolerance for $ amounts
    "phase": 0.5,             # half-phase (e.g. predicted P3, actual P2.5)
    "duration": 30.0,         # 30 days
    "percent": 5.0,           # 5 percentage points
}


def _score_distance(predicted: ParsedTarget, actual: ParsedTarget) -> Optional[float]:
    """Distance-based calibration in [0, 1]. None if units mismatch."""
    if predicted.unit != actual.unit:
        return None

    tol = _TOLERANCE.get(predicted.unit, 1.0)

    if predicted.unit == "usd":
        # Relative tolerance for currency
        if predicted.magnitude == 0:
            return 1.0 if actual.magnitude == 0 else 0.0
        rel_diff = abs(actual.magnitude - predicted.magnitude) / abs(predicted.magnitude)
        # rel_diff < tol → 1.0; > 4*tol → 0.0
        if rel_diff <= tol:
            return 1.0
        if rel_diff >= 4 * tol:
            return 0.0
        return 1.0 - (rel_diff - tol) / (3 * tol)

    # Direction check for pp: opposite sign is a hard penalty
    if predicted.unit == "pp":
        if (predicted.magnitude > 0) != (actual.magnitude > 0) and \
                abs(predicted.magnitude) > 0.5 and abs(actual.magnitude) > 0.5:
            # Predicted up, actually down (or vice versa) — large miscalibration
            distance = abs(actual.magnitude - predicted.magnitude)
            # Penalize harder than just the distance
            base = max(0.0, 1.0 - (distance / (4 * tol)))
            return base * 0.3

    distance = abs(actual.magnitude - predicted.magnitude)
    if distance <= tol:
        return 1.0
    if distance >= 4 * tol:
        return 0.0
    return 1.0 - (distance - tol) / (3 * tol)


def compute_numeric_calibration(
    *, target_value: Optional[str], actual_outcome: Optional[str],
) -> Optional[float]:
    """Try to compute a numeric calibration score.

    Returns None when either side fails to parse — caller falls back
    to the categorical 4-quadrant heuristic from outcome_detector.
    Returns 0.0–1.0 when both parse and units match.
    """
    pred = parse_target_value(target_value)
    if pred is None:
        return None
    act = parse_target_value(actual_outcome)
    if act is None:
        return None
    return _score_distance(pred, act)
