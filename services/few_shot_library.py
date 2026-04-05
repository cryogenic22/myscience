"""Few-shot prompt library for citation-dense LLM responses.

Provides curated exemplar Q&A pairs per intent type. Each exemplar
demonstrates the ideal response format with inline [N] citation markers
and [metrics] references. Wired into _build_context_block() to improve
citation density across all intent types.

Architecture:
  - Static exemplars stored as FewShotExemplar dataclasses
  - FewShotLibrary selects top exemplars per intent (default max 2)
  - format_context() renders exemplars as an LLM-readable block
  - Integrates downstream of CTXContextBuilder in the context pipeline
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FewShotExemplar:
    """A single exemplar Q&A pair for few-shot prompting."""

    intent: str
    question: str
    answer: str  # Must contain [N] citation markers
    entity_type: Optional[str] = None


# ── Curated exemplars ─────────────────────────────────────────────
# Each answer must contain 2+ [N] citation markers.
# Use [metrics] for metrics-sourced data.
# Keep answers to 3-4 sentences.

EXEMPLARS: dict[str, list[FewShotExemplar]] = {
    "dossier": [
        FewShotExemplar(
            intent="dossier",
            question="Tell me about semaglutide",
            answer=(
                "**Semaglutide** is a GLP-1 receptor agonist developed by "
                "**Novo Nordisk** [1]. With a pipeline score of **42.5** across "
                "**47 trials** [metrics], it has one of the strongest development "
                "programs in the GLP-1 space. The drug is currently in **Phase 4** "
                "with **40 post-marketing trials** and **5 active Phase 3 studies** "
                "[2]. Trial success rate stands at **82%** [metrics], significantly "
                "above the therapeutic area average."
            ),
            entity_type="drug",
        ),
        FewShotExemplar(
            intent="dossier",
            question="What do we know about Pfizer?",
            answer=(
                "**Pfizer** is a multinational pharmaceutical company with a "
                "diversified portfolio spanning **6 therapeutic areas** [1]. The "
                "company maintains **312 active trials** with a pipeline score of "
                "**89.2** [metrics], making it one of the top 3 pharma companies by "
                "development activity. Recent trial filings indicate expansion into "
                "**oncology** and **immunology**, with **23 Phase 2 programs** "
                "initiated in the last 12 months [2][3]."
            ),
            entity_type="company",
        ),
        FewShotExemplar(
            intent="dossier",
            question="Tell me about tirzepatide",
            answer=(
                "**Tirzepatide** is a dual GIP/GLP-1 receptor agonist developed by "
                "**Eli Lilly** [1]. It has demonstrated strong clinical activity with "
                "**28 trials** and a pipeline score of **35.8** [metrics]. The drug "
                "received FDA approval for type 2 diabetes and has **12 ongoing "
                "Phase 3 studies** across obesity and cardiovascular indications [2]. "
                "Its dual-agonist mechanism differentiates it from single-target "
                "GLP-1 therapies [3]."
            ),
            entity_type="drug",
        ),
        FewShotExemplar(
            intent="dossier",
            question="Tell me about GLP-1 receptor agonists",
            answer=(
                "**GLP-1 receptor agonists** are a mechanism class targeting the "
                "glucagon-like peptide-1 receptor, primarily used in **type 2 "
                "diabetes** and **obesity** [1]. The class includes **8 distinct "
                "molecules** with a combined **181 trials** and an aggregate pipeline "
                "score of **142.3** [metrics]. Key drugs include **semaglutide** "
                "(Novo Nordisk) and **tirzepatide** (Eli Lilly), which together "
                "account for **75 trials** [2].\n\n"
                "Development activity is concentrated in metabolic indications, "
                "but cardiovascular outcomes and NASH represent expanding frontiers "
                "with **18 dedicated trials** [3]. Trial success rates for the class "
                "average **74%** [metrics], above the all-indication benchmark."
            ),
            entity_type="mechanism",
        ),
        FewShotExemplar(
            intent="dossier",
            question="Brief me on the oncology landscape",
            answer=(
                "**Oncology** is the largest therapeutic area by trial volume, with "
                "**1,247 active trials** and a combined pipeline score of **342.7** "
                "[metrics]. The space is dominated by **immuno-oncology** approaches, "
                "particularly **PD-1/PD-L1 inhibitors** which account for **393 "
                "trials** across **18 tumor types** [1][2].\n\n"
                "Late-stage programs (Phase 3+) number **127** with a success rate "
                "of **54%** [metrics]. **Non-small cell lung cancer** and **melanoma** "
                "remain the most contested indications, while **hepatocellular "
                "carcinoma** and **gastric cancer** show accelerating enrollment [3]."
            ),
            entity_type="therapeutic_area",
        ),
        FewShotExemplar(
            intent="dossier",
            question="What do we know about Regeneron?",
            answer=(
                "**Regeneron** is a biotechnology company with data available on "
                "**14 trials** and a pipeline score of **11.2** [metrics]. The "
                "company is linked to the **immunology** and **oncology** therapeutic "
                "areas [1]. Data on specific pipeline composition is limited; "
                "additional enrichment may improve coverage.\n\n"
                "Available evidence shows activity in **monoclonal antibody** "
                "development [2], but detailed phase distribution and competitive "
                "positioning data is limited in the current dataset [metrics]."
            ),
            entity_type="company",
        ),
        FewShotExemplar(
            intent="dossier",
            question="Tell me about empagliflozin",
            answer=(
                "**Empagliflozin** is an **SGLT2 inhibitor** developed by "
                "**Boehringer Ingelheim** in partnership with **Eli Lilly** [1]. "
                "It has **34 trials** with a pipeline score of **22.7** [metrics]. "
                "The drug has established efficacy in **type 2 diabetes** and "
                "**heart failure**, with **8 Phase 4 post-marketing studies** [2].\n\n"
                "Within the SGLT2 class, empagliflozin competes directly with "
                "**dapagliflozin** (AstraZeneca), which has **41 trials** [metrics]. "
                "Empagliflozin's cardiovascular evidence base gives it a "
                "differentiated position in the heart failure segment [3]."
            ),
            entity_type="drug",
        ),
        FewShotExemplar(
            intent="dossier",
            question="Brief me on metformin safety profile",
            answer=(
                "**Metformin** is a biguanide and the most widely prescribed "
                "first-line therapy for **type 2 diabetes** [1]. With **156 trials** "
                "and a pipeline score of **18.4** [metrics], it has one of the "
                "deepest evidence bases of any diabetes drug. The majority of trials "
                "are **Phase 4** post-marketing studies (**112 of 156**) [2].\n\n"
                "Safety data from **FAERS** reports indicates a well-established "
                "adverse event profile, with **lactic acidosis** as the primary "
                "labeled risk [3]. Long-term safety is supported by decades of "
                "clinical use, and recent trials explore potential benefits in "
                "**oncology** and **aging** indications [metrics]."
            ),
            entity_type="drug",
        ),
    ],
    "compare": [
        FewShotExemplar(
            intent="compare",
            question="Compare semaglutide vs tirzepatide",
            answer=(
                "**Semaglutide** leads in development maturity with **47 trials** "
                "vs tirzepatide's **28** [metrics], a **1.7x advantage** in total "
                "clinical activity. However, **tirzepatide** shows faster pipeline "
                "momentum with **12 active Phase 3 studies** vs semaglutide's **5** "
                "[1][2]. Both target the GLP-1 pathway but tirzepatide's dual "
                "GIP/GLP-1 mechanism gives it a differentiated profile [3]. "
                "**Verdict**: semaglutide has the deeper evidence base, but "
                "tirzepatide is advancing more aggressively in late-stage trials."
            ),
            entity_type="drug",
        ),
        FewShotExemplar(
            intent="compare",
            question="Compare Novo Nordisk vs Eli Lilly",
            answer=(
                "**Novo Nordisk** maintains a larger pipeline with **89 active "
                "trials** vs Eli Lilly's **67** [metrics], but Eli Lilly leads "
                "in Phase 3 density with **31 late-stage programs** compared to "
                "Novo's **22** [1]. In shared therapeutic areas, Novo dominates "
                "diabetes while Lilly has broader oncology reach [2][3]. "
                "**Verdict**: Novo Nordisk has the larger metabolic franchise, "
                "but Eli Lilly is better positioned for therapeutic diversification."
            ),
            entity_type="company",
        ),
        FewShotExemplar(
            intent="compare",
            question="Compare pembrolizumab vs nivolumab",
            answer=(
                "**Pembrolizumab** (Merck) has a significantly larger trial "
                "footprint with **215 trials** vs nivolumab's **178** [metrics]. "
                "Both are PD-1 checkpoint inhibitors, but pembrolizumab covers "
                "**18 tumor types** vs nivolumab's **14** [1][2]. Trial success "
                "rates are comparable at **71%** vs **68%** [metrics]. "
                "**Verdict**: pembrolizumab has the broader indication portfolio "
                "while nivolumab maintains competitive parity in established indications."
            ),
            entity_type="drug",
        ),
    ],
    "landscape": [
        FewShotExemplar(
            intent="landscape",
            question="Show me the GLP-1 receptor agonist landscape",
            answer=(
                "The **GLP-1 receptor agonist** landscape is concentrated in "
                "**Diabetes Mellitus, Type 2**, which accounts for **62%** of "
                "total trial activity with **134 studies** [1][metrics]. "
                "**Obesity** is the fastest-growing segment with **47 trials**, "
                "a **3.2x increase** over the prior period [2]. Cardiovascular "
                "outcomes represent an emerging frontier with **18 dedicated "
                "trials** across MACE and heart failure endpoints [3]."
            ),
            entity_type="mechanism",
        ),
        FewShotExemplar(
            intent="landscape",
            question="What is the competitive landscape for SGLT2 inhibitors?",
            answer=(
                "**SGLT2 inhibitors** have clinical activity spanning **4 major "
                "therapeutic areas** [1]. Heart failure leads with **56 trials** "
                "and the highest pipeline score of **28.4** [metrics], followed by "
                "chronic kidney disease with **34 trials** [2]. The diabetes "
                "segment remains active but is increasingly mature with **89%** "
                "of trials in Phase 4 [3][metrics]."
            ),
            entity_type="mechanism",
        ),
        FewShotExemplar(
            intent="landscape",
            question="Show me the PD-1 inhibitor landscape",
            answer=(
                "The **PD-1 inhibitor** space is dominated by **non-small cell "
                "lung cancer**, accounting for **28%** of all trials with **93 "
                "studies** [1][metrics]. **Melanoma** and **renal cell carcinoma** "
                "are the next largest segments with **61** and **44 trials** "
                "respectively [2]. Emerging indications in **hepatocellular "
                "carcinoma** and **gastric cancer** show accelerating enrollment "
                "[3][metrics]."
            ),
            entity_type="mechanism",
        ),
    ],
    "pipeline": [
        FewShotExemplar(
            intent="pipeline",
            question="Show me Novo Nordisk's drug pipeline",
            answer=(
                "**Novo Nordisk** leads with a pipeline score of **89.2** "
                "across **89 active programs** [metrics]. The portfolio skews "
                "late-stage with **22 Phase 3 trials** and **34 Phase 4 "
                "post-marketing studies** [1]. Phase 2-to-3 advancement rate "
                "sits at **38%** [metrics], above the industry benchmark of "
                "~30%. Early-stage activity in **obesity** and **NASH** signals "
                "continued metabolic focus [2][3]."
            ),
            entity_type="company",
        ),
        FewShotExemplar(
            intent="pipeline",
            question="What is the pipeline strength in oncology?",
            answer=(
                "Oncology pipelines collectively score **342.7** across the "
                "top 10 developers [metrics]. **Phase 1/2 combination studies** "
                "dominate with **48%** of active trials, reflecting the shift "
                "toward immuno-oncology combinations [1]. Late-stage programs "
                "(Phase 3+) number **127**, with a success rate of **54%** "
                "[2][metrics], slightly below the therapeutic area target of 60%."
            ),
            entity_type=None,
        ),
        FewShotExemplar(
            intent="pipeline",
            question="Show drug pipeline for diabetes",
            answer=(
                "The diabetes pipeline includes **267 active trials** with a "
                "combined pipeline score of **198.5** [metrics]. GLP-1 agonists "
                "account for **42%** of late-stage programs [1]. **Dual-agonist "
                "therapies** are emerging with **18 Phase 2 studies** initiated "
                "in the past year [2]. Trial success rates stand at **74%** "
                "[metrics], well above the all-indication average of **62%** [3]."
            ),
            entity_type=None,
        ),
    ],
    "general": [
        FewShotExemplar(
            intent="general",
            question="What are the latest developments in GLP-1 therapies?",
            answer=(
                "GLP-1 therapies are experiencing rapid expansion beyond their "
                "original diabetes indication. **47 new trials** were initiated "
                "in the past quarter, with **obesity** and **cardiovascular "
                "outcomes** driving **68%** of new activity [1][2]. The "
                "competitive landscape now includes **8 distinct molecules** "
                "from **5 manufacturers** [metrics], up from 4 molecules two "
                "years ago. Oral formulations represent a key battleground with "
                "**12 active programs** [3]."
            ),
            entity_type=None,
        ),
        FewShotExemplar(
            intent="general",
            question="How many drugs are in our database for diabetes?",
            answer=(
                "The database contains **142 drugs** linked to diabetes "
                "indications, spanning **9 mechanism classes** [metrics]. "
                "**GLP-1 receptor agonists** are the most represented class "
                "with **34 entries** [1], followed by **SGLT2 inhibitors** at "
                "**28** and **DPP-4 inhibitors** at **22** [2]. Coverage is "
                "strongest for approved therapies (**89%** completeness) but "
                "thinner for preclinical candidates (**41%**) [3][metrics]."
            ),
            entity_type=None,
        ),
        FewShotExemplar(
            intent="general",
            question="What are the top therapeutic areas by trial activity?",
            answer=(
                "**Oncology** leads all therapeutic areas with **1,247 active "
                "trials** and a pipeline score of **342.7** [metrics]. "
                "**Metabolic diseases** rank second with **534 trials**, driven "
                "primarily by GLP-1 and SGLT2 programs [1][2]. **Immunology** "
                "rounds out the top three at **312 trials**, with notable growth "
                "in **autoimmune** indications [3][metrics]."
            ),
            entity_type=None,
        ),
    ],
}


class FewShotLibrary:
    """Retrieves and formats few-shot exemplars for LLM prompting."""

    def get_exemplars(
        self,
        intent: str,
        max_examples: int = 2,
        entity_type: Optional[str] = None,
    ) -> list[FewShotExemplar]:
        """Return top exemplars for an intent, limited by max_examples.

        Args:
            intent: The detected intent (dossier, compare, landscape, etc.).
            max_examples: Maximum number of exemplars to return (default 2).
            entity_type: Optional filter to prefer exemplars matching entity type.

        Returns:
            List of FewShotExemplar, up to max_examples.
        """
        pool = EXEMPLARS.get(intent, [])
        if not pool:
            return []

        # If entity_type specified, sort matching exemplars first
        if entity_type:
            matching = [e for e in pool if e.entity_type == entity_type]
            non_matching = [e for e in pool if e.entity_type != entity_type]
            pool = matching + non_matching

        return pool[:max_examples]

    def format_context(self, exemplars: list[FewShotExemplar]) -> str:
        """Format exemplars as an LLM context block.

        Produces a block like:
            === Example Q&A (follow this citation style) ===

            Q: Tell me about semaglutide
            A: **Semaglutide** is a GLP-1 receptor agonist...

            Q: What do we know about Pfizer?
            A: **Pfizer** is a multinational...

        Args:
            exemplars: List of FewShotExemplar to format.

        Returns:
            Formatted string block ready for LLM context injection.
        """
        if not exemplars:
            return ""

        parts = ["=== Example Q&A (follow this citation style) ==="]
        for ex in exemplars:
            parts.append(f"\nQ: {ex.question}\nA: {ex.answer}")

        return "\n".join(parts)
