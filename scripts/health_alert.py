"""Turn a connector_health.py --json report into a GitHub-issue alert.

The scheduled operational-health gate already fails (reds the CI tab) when a
source is RED. That's passive — someone has to look. This renders the same
verdict into a single, idempotent tracking issue so rot is pushed, not pulled.

Pure decision + rendering here (unit-tested, DB-free); the `gh issue`
create/update/close glue lives in operational-health.yml. Deferred sources (no
source wired yet — KNOWN_DEFERRED_SOURCES) never alert: a legitimately-empty
source is not rot (conservation principle #2 — legitimate-empty != broken-empty).

Usage (in CI):
    python scripts/connector_health.py --json > health.json
    python scripts/health_alert.py --input health.json --body-out body.md
    # writes should_alert/title to $GITHUB_OUTPUT; the workflow opens/updates/closes
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Stable title so the workflow finds and UPDATES one issue instead of spamming.
ALERT_TITLE = "Connector health: degraded sources"


def _active(scores: list[dict]) -> list[dict]:
    """Drop deferred sources — they have no source wired and must not alert."""
    return [s for s in scores if not s.get("deferred")]


def _unwrap(data) -> tuple[list, list, dict | None]:
    """connector_health --json used to emit a bare list of source scores; it now
    emits an envelope {"sources", "dlq", "ledger"}. Accept both so an old report
    (or a hand-run against an old checkout) still parses. Returns (sources, ledger,
    dlq)."""
    if isinstance(data, dict):
        return data.get("sources", []), data.get("ledger", []), data.get("dlq")
    return data, [], None


def build_alert(
    scores: list[dict],
    *,
    alert_on_amber: bool = False,
    as_of: str = "",
    ledger: list[dict] | None = None,
    dlq: dict | None = None,
) -> dict:
    """Decide whether to alert and render the issue body.

    Returns {should_alert, red, amber, ledger, dlq_red, title, body}. `red`/`amber`
    /`ledger` are name lists; `body` is GitHub-flavoured markdown. A frozen ledger
    or a growing DLQ backlog alerts on their own — the whole point of surfacing them
    is that a spine freeze / dead-letter bleed must never be silent behind green
    sources (the 27-Jun freeze reddened nothing a human saw).
    """
    active = _active(scores)
    red = [s for s in active if (s.get("verdict") or "").upper() == "RED"]
    amber = [s for s in active if (s.get("verdict") or "").upper() == "AMBER"]
    ledger_stale = [l for l in (ledger or []) if not l.get("healthy", True)]
    dlq_red = bool(dlq) and (dlq.get("verdict") or "").upper() == "RED"
    should_alert = (
        bool(red)
        or (alert_on_amber and bool(amber))
        or bool(ledger_stale)
        or dlq_red
    )

    body = _render_body(
        red, amber, total=len(active), as_of=as_of, alert_on_amber=alert_on_amber,
        ledger_stale=ledger_stale, dlq=dlq if dlq_red else None,
    )
    return {
        "should_alert": should_alert,
        "red": [s.get("source") for s in red],
        "amber": [s.get("source") for s in amber],
        "ledger": [l.get("source") for l in ledger_stale],
        "dlq_red": dlq_red,
        "title": ALERT_TITLE,
        "body": body,
    }


def _row(s: dict) -> str:
    notes = "; ".join(s.get("notes") or []) or "—"
    age = s.get("age_days")
    sla = s.get("sla_days")
    age_str = f"{age}d / {sla}d" if age is not None and sla is not None else "—"
    linked = s.get("linked_pct")
    linked_str = f"{linked}%" if linked is not None else "—"
    return (
        f"| `{s.get('source')}` | {s.get('verdict')} | {s.get('table')} | "
        f"{s.get('rows', '—')} | {age_str} | {linked_str} | {notes} |"
    )


def _render_body(red: list[dict], amber: list[dict], *, total: int, as_of: str,
                 alert_on_amber: bool, ledger_stale: list[dict] | None = None,
                 dlq: dict | None = None) -> str:
    ledger_stale = ledger_stale or []
    lines: list[str] = []
    if red:
        lines.append(f"**{len(red)} RED** source(s) — over SLA, no terminal status, or 0-row anomaly.")
    if amber and alert_on_amber:
        lines.append(f"**{len(amber)} AMBER** source(s) — stale but under 2x SLA.")
    if ledger_stale:
        names = ", ".join(f"`{l.get('source')}`" for l in ledger_stale)
        lines.append(
            f"**Ledger FROZEN** — {names} over freshness SLA. The knowledge spine "
            "(facts/evidence that every lens reads) has stopped converging; check the "
            "scheduled ledger-convergence job."
        )
    if dlq:
        lines.append(
            f"**DLQ bleed** — dead-letter backlog is growing ({dlq.get('pending_total', '?')} "
            "pending). A connector is silently failing rows; triage the newest cause."
        )
    if not red and not amber and not ledger_stale and not dlq:
        lines.append("All active sources GREEN.")
    lines.append("")
    shown = red + (amber if alert_on_amber else [])
    if shown:
        lines.append("| source | verdict | table | rows | age/SLA | linked | notes |")
        lines.append("|---|---|---|---|---|---|---|")
        lines.extend(_row(s) for s in shown)
        lines.append("")
    lines.append(f"_{len(red)} red, {len(amber)} amber of {total} active sources._")
    if as_of:
        lines.append(f"_Checked: {as_of}._")
    lines.append("")
    lines.append("Source of truth: `scripts/connector_health.py` (Lane 2, operational-health.yml).")
    return "\n".join(lines)


def _emit_output(key: str, value: str) -> None:
    """Write a GITHUB_OUTPUT line if running in Actions; else print for local use."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a connector-health alert from --json output")
    ap.add_argument("--input", default="", help="health JSON file (default: stdin)")
    ap.add_argument("--body-out", default="", help="write the issue body markdown here")
    ap.add_argument("--alert-on-amber", action="store_true", help="also alert on AMBER")
    ap.add_argument("--as-of", default="", help="timestamp string for the body")
    args = ap.parse_args()

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
    scores, ledger, dlq = _unwrap(json.loads(raw))
    result = build_alert(
        scores, alert_on_amber=args.alert_on_amber, as_of=args.as_of,
        ledger=ledger, dlq=dlq,
    )

    if args.body_out:
        with open(args.body_out, "w", encoding="utf-8") as f:
            f.write(result["body"])

    _emit_output("should_alert", "true" if result["should_alert"] else "false")
    _emit_output("title", result["title"])
    print(
        f"alert={result['should_alert']} red={result['red']} amber={result['amber']} "
        f"ledger={result['ledger']} dlq_red={result['dlq_red']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
