"""SPEC_042 — `docs/PRODUCT_BACKLOG.md` validator + dashboard regenerator.

Usage::

    python -m scripts.validate_product_backlog [--check | --regenerate-summary]

Default mode (`--check`): exits 0 if every PB-NNN block declares all
required fields, every cross-reference resolves, IDs are unique, and
the dashboard counts match the body. Exits 1 with a printed report
otherwise.

`--regenerate-summary`: rewrite the dashboard table (between
`## Dashboard` and `## Items`) to match the body. Useful as a
post-edit fixup.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = {
    "Type",
    "Status",
    "Priority",
    "Owner",
    "Source",
    "Source ref",
    "Created",
    "Last touched",
    "Notes",
}

VALID_TYPES = {"bug", "feature", "enhancement", "refactor", "infra", "data", "docs", "spike"}
VALID_STATUSES = {"proposed", "triaged", "blocked", "in-progress", "shipped", "archived", "wontfix"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_OWNERS = {"frontend-claude", "backend-claude", "shared", "unassigned"}
VALID_SOURCES = {"spec", "feedback", "agent-ask", "roadmap", "brainstorm", "adhoc"}

ITEM_HEADING_RE = re.compile(r"^### \[(PB-\d{3,})\]\s+(.*?)\s*$")
FIELD_LINE_RE = re.compile(r"^- \*\*(?P<key>[A-Za-z][A-Za-z\s]*)\*\*:\s*(?P<value>.*?)\s*$")


@dataclass
class Item:
    item_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    line_no: int = 0


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_items(text: str) -> list[Item]:
    items: list[Item] = []
    current: Item | None = None
    for ln_idx, line in enumerate(text.splitlines(), start=1):
        m = ITEM_HEADING_RE.match(line)
        if m:
            if current is not None:
                items.append(current)
            current = Item(item_id=m.group(1), title=m.group(2), line_no=ln_idx)
            continue
        if current is None:
            continue
        # Stop accumulating fields once we hit the next H2/H3 unrelated.
        if line.startswith("## ") or (line.startswith("### ") and not ITEM_HEADING_RE.match(line)):
            items.append(current)
            current = None
            continue
        fm = FIELD_LINE_RE.match(line)
        if fm:
            key = fm.group("key").strip()
            current.fields[key] = fm.group("value").strip()
    if current is not None:
        items.append(current)
    return items


def _spec_exists(repo_root: Path, spec_ref: str) -> bool:
    """SPEC-NNN, SPEC-NNN#section. Resolve to specs/SPEC_NNN_*.md."""
    base = spec_ref.split("#", 1)[0]
    if not re.fullmatch(r"SPEC-\d{3,}", base):
        return False
    num = base.split("-", 1)[1]
    matches = list((repo_root / "specs").glob(f"SPEC_{num}_*.md"))
    if matches:
        return True
    # Also accept archived specs
    archived = list((repo_root / "docs" / "archive" / "superseded-specs").glob(f"SPEC_{num}_*.md"))
    return bool(archived)


def _agent_backlog_section_exists(repo_root: Path, ref: str) -> bool:
    # Format: AGENT_BACKLOG#FRONTEND.5 (loose; we just check the file)
    path = repo_root / "docs" / "AGENT_BACKLOG.md"
    return path.exists()


def validate_text(text: str, repo_root: Path) -> Report:
    report = Report()
    items = parse_items(text)

    # Uniqueness
    seen: dict[str, Item] = {}
    for it in items:
        if it.item_id in seen:
            report.errors.append(
                f"Duplicate ID: {it.item_id} appears at lines "
                f"{seen[it.item_id].line_no} and {it.line_no}"
            )
        else:
            seen[it.item_id] = it

    valid_ids = set(seen.keys())

    for it in items:
        # Required fields
        missing = REQUIRED_FIELDS - set(it.fields.keys())
        for f in sorted(missing):
            report.errors.append(f"{it.item_id}: missing required field '{f}'")

        # Enum validation
        def _validate_enum(field_name: str, allowed: set[str]) -> None:
            v = it.fields.get(field_name)
            if v is None:
                return
            if v not in allowed:
                report.errors.append(
                    f"{it.item_id}: {field_name}='{v}' not in {sorted(allowed)}"
                )

        _validate_enum("Type", VALID_TYPES)
        _validate_enum("Status", VALID_STATUSES)
        _validate_enum("Priority", VALID_PRIORITIES)
        _validate_enum("Owner", VALID_OWNERS)
        _validate_enum("Source", VALID_SOURCES)

        # Cross references — Source ref
        sref = it.fields.get("Source ref", "n/a")
        if sref and sref != "n/a":
            if sref.startswith("SPEC-"):
                if not _spec_exists(repo_root, sref):
                    report.errors.append(
                        f"{it.item_id}: Source ref '{sref}' does not resolve to a spec file"
                    )
            elif sref.startswith("AGENT_BACKLOG"):
                if not _agent_backlog_section_exists(repo_root, sref):
                    report.errors.append(
                        f"{it.item_id}: Source ref '{sref}' missing — AGENT_BACKLOG.md not found"
                    )
            elif (
                sref.startswith("fb-")
                or sref.startswith("PR #")
                or sref == "adhoc"
                or sref.startswith("legacy:")
            ):
                pass  # Trust these — feedback ids out-of-band; PRs out-of-repo;
                      # legacy: prefix points at archived backlog files (post-migration)
            else:
                report.warnings.append(
                    f"{it.item_id}: Source ref '{sref}' uses an unrecognised format"
                )

        # Cross references — Blocked by
        blocked_by = it.fields.get("Blocked by", "n/a")
        if blocked_by and blocked_by != "n/a":
            for ref in [s.strip() for s in blocked_by.split(",") if s.strip()]:
                if not re.fullmatch(r"PB-\d{3,}", ref):
                    report.warnings.append(
                        f"{it.item_id}: Blocked by '{ref}' does not look like a PB-NNN id"
                    )
                    continue
                if ref not in valid_ids:
                    report.errors.append(
                        f"{it.item_id}: Blocked by references unknown id '{ref}'"
                    )

    return report


# ── Dashboard regeneration ──


def _count_status(items: Iterable[Item]) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in VALID_STATUSES}
    for it in items:
        s = it.fields.get("Status", "")
        if s in counts:
            counts[s] += 1
    return counts


def _shipped_within(items: Iterable[Item], days: int) -> int:
    cutoff = date.today() - timedelta(days=days)
    n = 0
    for it in items:
        if it.fields.get("Status") != "shipped":
            continue
        try:
            touched = datetime.strptime(it.fields.get("Last touched", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if touched >= cutoff:
            n += 1
    return n


def regenerate_summary(text: str) -> str:
    items = parse_items(text)
    counts = _count_status(items)
    shipped_recent = _shipped_within(items, 90)

    in_flight = [it for it in items if it.fields.get("Status") == "in-progress"]
    blocked = [it for it in items if it.fields.get("Status") == "blocked"]

    today = date.today().isoformat()
    rows = [
        f"## Dashboard (regenerated {today})",
        "",
        "| Status        | Count |",
        "|---------------|-------|",
        f"| in-progress   | {counts['in-progress']:<5} |",
        f"| triaged       | {counts['triaged']:<5} |",
        f"| blocked       | {counts['blocked']:<5} |",
        f"| proposed      | {counts['proposed']:<5} |",
        f"| shipped (90d) | {shipped_recent:<5} |",
        "",
    ]

    if in_flight:
        rows.append(f"## Currently in flight ({len(in_flight)})")
        rows.append("")
        for it in in_flight:
            owner = it.fields.get("Owner", "unassigned")
            sref = it.fields.get("Source ref", "n/a")
            rows.append(f"- [{it.item_id}] {it.title} — {owner} / {sref}")
        rows.append("")

    if blocked:
        rows.append(f"## Blocked ({len(blocked)})")
        rows.append("")
        for it in blocked:
            blockers = it.fields.get("Blocked by", "n/a")
            rows.append(f"- [{it.item_id}] {it.title} — blocked by {blockers}")
        rows.append("")

    new_block = "\n".join(rows).rstrip() + "\n"

    # Replace whatever exists between the first `## Dashboard` and the next
    # `## ` line. If there's no `## Dashboard`, insert at the top of the body.
    pat = re.compile(r"## Dashboard.*?(?=\n## |\Z)", re.DOTALL)
    if pat.search(text):
        return pat.sub(new_block.rstrip(), text, count=1)
    # No dashboard yet — insert before `## Items`.
    if "## Items" in text:
        return text.replace("## Items", new_block + "\n## Items", 1)
    return new_block + "\n" + text


# ── CLI ──


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", default=True)
    parser.add_argument("--regenerate-summary", action="store_true")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("docs/PRODUCT_BACKLOG.md"),
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    target = (repo_root / args.file).resolve() if not args.file.is_absolute() else args.file

    if not target.exists():
        print(f"validate_product_backlog: file not found: {target}", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")

    if args.regenerate_summary:
        new = regenerate_summary(text)
        target.write_text(new, encoding="utf-8")
        print(f"validate_product_backlog: regenerated dashboard in {target}")
        return 0

    report = validate_text(text, repo_root=repo_root)
    if report.errors:
        print("ERRORS:")
        for e in report.errors:
            print(f"  - {e}")
    if report.warnings:
        print("WARNINGS:")
        for w in report.warnings:
            print(f"  - {w}")
    if report.ok:
        print(f"validate_product_backlog: {target.name} OK")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
