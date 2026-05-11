"""SPEC_042 — one-shot migrator for legacy backlog files.

Reads the four legacy files described in SPEC_042 §10a.6, extracts the
items that are still actually current, and emits PB-NNN rows ready to
paste into `docs/PRODUCT_BACKLOG.md`.

Library functions are pure (unit-testable). The CLI (`__main__`)
orchestrates them and writes the output to a file or stdout.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ── Per-file extraction strategies ──


SHIPPED_PHASES = ("Phase 0", "Phase 1", "Phase 2", "Current State")


def extract_roadmap_items(text: str) -> list[dict[str, str]]:
    """Per §10a.6 — skip already-shipped phases (0-2) and 'Current State'."""
    out: list[dict[str, str]] = []
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None

    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = (line[3:].strip(), [])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        sections.append(current)

    for heading, lines in sections:
        if any(heading.startswith(prefix) for prefix in SHIPPED_PHASES):
            continue
        # Top-level non-phase sections (Implementation Timeline,
        # Critical Dependencies, Files Created etc.) — skip.
        if not heading.startswith("Phase"):
            continue
        body = "\n".join(lines)
        # Each `### ` is one extractable item
        for m in re.finditer(r"^### (.+?)$", body, flags=re.MULTILINE):
            title = m.group(1).strip()
            out.append({"title": title, "source_section": heading})
    return out


_AGENT_HEADING_RE = re.compile(r"^## \[(BACKEND|FRONTEND|PROTOCOL)\]\s*(.+?)$", re.MULTILINE)
_AGENT_NESTED_RE = re.compile(r"^### \[(BACKEND|FRONTEND|PROTOCOL)\]\s*(.+?)$", re.MULTILINE)


def extract_agent_backlog_stubs(text: str) -> list[dict[str, str]]:
    """Each `Status: open` ask becomes a single PB-stub.

    Both top-level (`## [TAG] Title`) and nested (`### [TAG] Title`) headings are
    accepted.
    """
    out: list[dict[str, str]] = []
    # Split text into per-heading blocks. Walk the whole file once.
    headings = list(_AGENT_HEADING_RE.finditer(text)) + list(_AGENT_NESTED_RE.finditer(text))
    headings.sort(key=lambda m: m.start())
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]
        if "Status: open" in block:
            out.append(
                {
                    "tag": m.group(1),
                    "title": m.group(2).strip(),
                }
            )
    return out


def extract_root_backlog_items(text: str) -> list[dict[str, str]]:
    """Pull `### ` items from the still-relevant sections of root BACKLOG.md."""
    relevant_sections = (
        "In Progress",
        "Planned",
        "Future / Aspirational",
        "UI & Intelligence Upgrades",
        "UX & Intelligence Overhaul (v2)",
        "Implementation Order (UX Overhaul v2)",
    )
    out: list[dict[str, str]] = []
    current_section: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if line.startswith("### ") and current_section in relevant_sections:
            out.append({"title": line[4:].strip(), "source_section": current_section})
    return out


def extract_docs_backlog_items(text: str) -> list[dict[str, str]]:
    """`docs/backlog.md` is small (6 items). Pull every `### ` heading."""
    out: list[dict[str, str]] = []
    for m in re.finditer(r"^### (.+?)$", text, flags=re.MULTILINE):
        out.append({"title": m.group(1).strip()})
    return out


# ── PB row formatting ──


@dataclass
class PBRow:
    pb_id: str
    title: str
    type_: str
    status: str
    priority: str
    owner: str
    source: str
    source_ref: str
    created: str
    last_touched: str
    notes: str
    blocked_by: str = "n/a"


def format_pb_row(row: PBRow) -> str:
    lines = [
        f"### [{row.pb_id}] {row.title}",
        f"- **Type**: {row.type_}",
        f"- **Status**: {row.status}",
        f"- **Priority**: {row.priority}",
        f"- **Owner**: {row.owner}",
        f"- **Source**: {row.source}",
        f"- **Source ref**: {row.source_ref}",
        f"- **Blocked by**: {row.blocked_by}",
        f"- **Created**: {row.created}",
        f"- **Last touched**: {row.last_touched}",
        f"- **Notes**: {row.notes}",
    ]
    return "\n".join(lines)


# ── CLI ──


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repo root (defaults to the parent of this script's package).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the consolidated rows to this file (default stdout).",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()

    files = {
        "ROADMAP.md": (root / "ROADMAP.md", extract_roadmap_items, "roadmap"),
        "BACKLOG.md": (root / "BACKLOG.md", extract_root_backlog_items, "roadmap"),
        "docs/backlog.md": (root / "docs" / "backlog.md", extract_docs_backlog_items, "roadmap"),
        "AGENT_BACKLOG.md": (
            root / "docs" / "AGENT_BACKLOG.md",
            extract_agent_backlog_stubs,
            "agent-ask",
        ),
    }

    rows: list[PBRow] = []
    pb_counter = 1
    today = "2026-05-09"

    for file_label, (path, extractor, source) in files.items():
        if not path.exists():
            continue
        items = extractor(path.read_text(encoding="utf-8"))
        for it in items:
            sref = (
                f"AGENT_BACKLOG#{it.get('tag', '')}"
                if source == "agent-ask"
                else f"legacy:{file_label}"
            )
            rows.append(
                PBRow(
                    pb_id=f"PB-{pb_counter:03d}",
                    title=it["title"][:120],
                    type_="feature",
                    status="proposed",
                    priority="medium",
                    owner="unassigned",
                    source=source,
                    source_ref=sref,
                    created=today,
                    last_touched=today,
                    notes=f"Migrated from {file_label}"
                    + (
                        f" (section: {it['source_section']})"
                        if "source_section" in it
                        else ""
                    ),
                )
            )
            pb_counter += 1

    output_lines = [format_pb_row(r) for r in rows]
    output = "\n\n".join(output_lines) + "\n"

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(
            f"migrate_legacy_backlogs: wrote {len(rows)} PB-rows to {args.out}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
