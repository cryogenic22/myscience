"""Literature section parser — converts PMC full_text into navigable section tree.

PMC articles are stored with ## markdown headers (from XML <sec> tags).
This module parses that flat text into a hierarchical structure for the
Literature Explorer frontend.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# Matches ## or ### at start of line
_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def parse_sections(
    full_text: str | None,
    abstract: str | None,
) -> list[dict]:
    """Parse PMC full_text into a section tree.

    Returns list of:
        {"id": "s-0", "title": "Abstract", "level": 1,
         "content": "...", "children": [...]}

    Splits on ## (level 1) and ### (level 2) markdown headers.
    Abstract from PubMed always comes first if provided.
    If PMC text has its own ## Abstract section, it's skipped (dedup).
    """
    if not full_text and not abstract:
        return []

    sections: list[dict] = []
    section_counter = 0

    # 1. Add PubMed abstract as first section
    if abstract and abstract.strip():
        sections.append({
            "id": f"s-{section_counter}",
            "title": "Abstract",
            "level": 1,
            "content": abstract.strip(),
            "children": [],
        })
        section_counter += 1

    # 2. Parse full_text if available
    if full_text and full_text.strip():
        has_headers = bool(_HEADER_RE.search(full_text))

        if not has_headers:
            # No section markers — wrap as single "Full Text" section
            sections.append({
                "id": f"s-{section_counter}",
                "title": "Full Text",
                "level": 1,
                "content": full_text.strip(),
                "children": [],
            })
        else:
            # Split on headers
            has_pubmed_abstract = abstract and abstract.strip()
            raw_sections = _split_by_headers(full_text)

            for title, level, content in raw_sections:
                # Skip PMC abstract section if we already have PubMed abstract
                if has_pubmed_abstract and title.lower().strip() == "abstract":
                    continue

                sid = f"s-{section_counter}"

                if level == 1:
                    sections.append({
                        "id": sid,
                        "title": title,
                        "level": 1,
                        "content": content,
                        "children": [],
                    })
                    section_counter += 1
                elif level == 2 and sections:
                    # Attach as child of the last level-1 section
                    parent = sections[-1]
                    child_idx = len(parent["children"])
                    parent["children"].append({
                        "id": f"{parent['id']}-{child_idx}",
                        "title": title,
                        "level": 2,
                        "content": content,
                        "children": [],
                    })
                else:
                    # Level 2 with no parent, or deeper — treat as level 1
                    sections.append({
                        "id": sid,
                        "title": title,
                        "level": 1,
                        "content": content,
                        "children": [],
                    })
                    section_counter += 1

    return sections


def _split_by_headers(text: str) -> list[tuple[str, int, str]]:
    """Split text on ## and ### headers.

    Returns list of (title, level, content) tuples.
    Level 1 = ##, Level 2 = ###.
    Content before the first header is discarded (usually empty).
    """
    results: list[tuple[str, int, str]] = []
    matches = list(_HEADER_RE.finditer(text))

    if not matches:
        return []

    for i, match in enumerate(matches):
        hashes = match.group(1)
        title = match.group(2).strip()
        level = len(hashes) - 1  # ## = 1, ### = 2

        # Content runs from end of this header to start of next header
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()

        results.append((title, level, content))

    return results
