"""DI-3 — dimension-aware synthesis.

Turns the decomposition matrix (DI-2) into an analyst-grade answer:
  * one section PER dimension, citing the grounded cell facts;
  * covered dimensions cite real facts (with source class/label);
  * uncovered dimensions are stated as explicit GAPS — never invented
    ("No pricing facts for tirzepatide in the KB — flagged for collection").

Two surfaces:
  * synthesize_matrix(matrix)  → a fully-grounded, deterministic markdown answer
    (the floor; correct even with the LLM off — no fabrication risk).
  * matrix_to_context(matrix) + matrix_insight_lead(matrix) → structured context
    the EXISTING llm.synthesize_comparison consumes, so the chat answer reflects
    the matrix without rewriting the LLM synthesizer (a sibling agent owns it).

This is the spec's "synthesize per dimension with citations; gaps are stated,
never invented" — pairs with the H2/H3 grounding loops downstream.
"""

from __future__ import annotations

from typing import Optional

from services.domain_intelligence.planner import QuestionMatrix

# Cap facts cited per cell in the narrative so a rich dimension stays readable.
_MAX_CITED = 3


def _label_for(matrix: QuestionMatrix, dimension_key: str) -> str:
    for d in matrix.dimensions:
        if d.key == dimension_key:
            return d.label
    return dimension_key.replace("_", " ").capitalize()


def _entity_name(matrix: QuestionMatrix, entity_id: str) -> str:
    for e in matrix.entities:
        if e["entity_id"] == entity_id:
            return e["label"]
    return entity_id


def synthesize_matrix(matrix: Optional[QuestionMatrix]) -> str:
    """Grounded, deterministic per-dimension narrative. Never fabricates: a cell
    with no facts becomes an explicit gap line, not invented prose."""
    if matrix is None:
        return ""

    names = [e["label"] for e in matrix.entities]
    lines: list[str] = []
    lines.append(f"**{' vs '.join(names)}** — decomposed across "
                 f"{len(matrix.dimensions)} dimensions a domain analyst examines.")
    lines.append("")

    for dim in matrix.dimensions:
        lines.append(f"### {dim.label}")
        for e in matrix.entities:
            eid = e["entity_id"]
            name = e["label"]
            cell = matrix.cell(dim.key, eid)
            if cell is None or cell.coverage == "gap":
                # Honest gap — never invented.
                lines.append(
                    f"- **{name}**: _gap_ — no {dim.label.lower()} facts in the "
                    f"knowledge base; flagged for collection."
                )
                continue
            cited = cell.facts[:_MAX_CITED]
            thin = " _(thin)_" if cell.coverage == "thin" else ""
            lines.append(f"- **{name}**{thin}:")
            for f in cited:
                src = f.get("source_label") or f.get("fact_class") or "fact"
                lines.append(f"    - {f['claim']}  _[{f.get('fact_class', 'fact')}· {src}]_")
        lines.append("")

    # Closing honesty note: enumerate the gaps so nothing thin is glossed over.
    gaps = matrix.gaps()
    if gaps:
        gap_labels = [_label_for(matrix, g) for g in gaps]
        lines.append(
            f"_Data gaps (stated, not inferred): {', '.join(gap_labels)}._"
        )

    return "\n".join(lines).strip()


def matrix_to_context(matrix: Optional[QuestionMatrix]) -> str:
    """Structured, grounded context for the LLM. Every cell is labeled with its
    coverage so the model CANNOT silently fill a gap — gaps are marked GAP and
    must be reported as such."""
    if matrix is None:
        return ""

    out: list[str] = ["DECOMPOSITION MATRIX (grounded facts per dimension — "
                      "do NOT invent for any cell marked GAP):"]
    for dim in matrix.dimensions:
        out.append(f"\n## {dim.label} (sub-question: {dim.sub_question})")
        for e in matrix.entities:
            eid = e["entity_id"]
            cell = matrix.cell(dim.key, eid)
            if cell is None or cell.coverage == "gap":
                out.append(f"- {e['label']}: GAP — no facts; report as a gap, do not infer.")
                continue
            tag = cell.coverage.upper()
            out.append(f"- {e['label']} [{tag}]:")
            for f in cell.facts[:_MAX_CITED]:
                out.append(f"    • {f['claim']} [{f.get('fact_class', 'fact')}]")
    return "\n".join(out)


def matrix_insight_lead(matrix: Optional[QuestionMatrix]) -> str:
    """A one-line lead differentiator drawn from the matrix's lead_with shape.
    Grounded: picks the first dimension where BOTH entities are covered and the
    rendered facts differ (a real point of difference)."""
    if matrix is None or len(matrix.entities) < 2:
        return ""

    a, b = matrix.entities[0], matrix.entities[1]
    for dim in matrix.dimensions:
        ca = matrix.cell(dim.key, a["entity_id"])
        cb = matrix.cell(dim.key, b["entity_id"])
        if not ca or not cb:
            continue
        if ca.coverage != "gap" and cb.coverage != "gap":
            ta = ca.facts[0]["claim"] if ca.facts else ""
            tb = cb.facts[0]["claim"] if cb.facts else ""
            if ta and tb and ta != tb:
                return (f"Key differentiator — {dim.label}: "
                        f"{a['label']}: {ta}; {b['label']}: {tb}.")
    # No covered-vs-covered difference found — lead with the coverage contrast.
    summ = matrix.coverage_summary()
    covered = [d.label for d in matrix.dimensions if summ.get(d.key) == "covered"]
    if covered:
        return f"Both compared across {', '.join(covered[:3])} and more."
    return ""
