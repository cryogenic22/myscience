"""SPL XML → LOINC-keyed section parser.

SPEC-016 §7 swimlane A4.1 (Cycle 5).

DailyMed serves drug labels in HL7 SPL (Structured Product Labeling)
XML. Every meaningful section is wrapped in <section> with a LOINC
<code> identifying the section type:

  34066-1 BOXED WARNING
  34067-9 INDICATIONS AND USAGE
  34068-7 DOSAGE AND ADMINISTRATION
  34070-3 CONTRAINDICATIONS
  43685-7 WARNINGS AND PRECAUTIONS
  34071-1 ADVERSE REACTIONS
  34073-7 DRUG INTERACTIONS
  43684-0 USE IN SPECIFIC POPULATIONS
  ...

This parser flattens each section's body text (paragraphs, lists,
tables) into a normalised plain-text string. The Cycle 6 diff service
then compares section text across two SPL revisions for the same
setid and emits label_change events on real edits.

Pure function — no I/O, takes an XML string, returns a list of
SplSection dataclasses. Tested against fixture XML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree as ET


SPL_NS = "urn:hl7-org:v3"
NS = {"hl7": SPL_NS}


# ────────────────────────────────────────────────────────────────────
# SplSection — one LOINC-keyed section
# ────────────────────────────────────────────────────────────────────


@dataclass
class SplSection:
    loinc_code: str
    display_name: str
    title: str
    text: str


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _local(tag: str) -> str:
    """Strip the {namespace} prefix from an element tag."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text_of(element: ET.Element) -> str:
    """Recursively flatten an element's text content into one string.

    Preserves newlines between block-level children (<paragraph>,
    <list>, <item>, <table>) so the output is reasonable to diff.
    """
    BLOCK_TAGS = {"paragraph", "list", "item", "table", "tr", "td", "th",
                  "title", "br"}

    def walk(el: ET.Element) -> str:
        chunks: list[str] = []
        if el.text:
            chunks.append(el.text)
        for child in el:
            tag = _local(child.tag)
            inner = walk(child)
            if tag in BLOCK_TAGS:
                chunks.append("\n" + inner + "\n")
            else:
                chunks.append(inner)
            if child.tail:
                chunks.append(child.tail)
        return "".join(chunks)

    raw = walk(element)
    # Collapse repeated whitespace, strip per-line
    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


def _find_first(element: ET.Element, *local_tags: str) -> Optional[ET.Element]:
    """Find the first direct child whose local tag matches any of the
    provided tags. Namespace-agnostic."""
    for child in element:
        if _local(child.tag) in local_tags:
            return child
    return None


def _section_to_model(section_el: ET.Element) -> Optional[SplSection]:
    code_el = _find_first(section_el, "code")
    if code_el is None:
        return None
    loinc_code = code_el.attrib.get("code")
    if not loinc_code:
        return None
    display_name = code_el.attrib.get("displayName", "")

    title_el = _find_first(section_el, "title")
    title = (title_el.text or "").strip() if title_el is not None else ""

    text_el = _find_first(section_el, "text")
    text = _text_of(text_el) if text_el is not None else ""

    return SplSection(
        loinc_code=loinc_code,
        display_name=display_name,
        title=title,
        text=text,
    )


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def parse_sections(xml_text: str) -> list[SplSection]:
    """Parse SPL XML and return one SplSection per LOINC-coded section.

    Skips:
      - Sections without a <code code="..."/>
      - Sections with empty or missing LOINC codes

    Raises ParseError on malformed XML.
    """
    root = ET.fromstring(xml_text)
    sections: list[SplSection] = []
    for section_el in root.iter():
        if _local(section_el.tag) != "section":
            continue
        model = _section_to_model(section_el)
        if model is not None:
            sections.append(model)
    return sections


def sections_to_dict(sections: list[SplSection]) -> dict[str, SplSection]:
    """Index sections by LOINC code for quick lookups by the diff service."""
    return {s.loinc_code: s for s in sections}
