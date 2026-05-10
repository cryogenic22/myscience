# GraphRAG for Clinical Document Authoring: When It Makes Sense and When It Doesn't

## Executive Summary

GraphRAG is a powerful pattern — but it solves a specific class of problems: **multi-hop retrieval over interconnected entities where vector similarity alone misses critical context**. For AI-assisted *authoring* of clinical documents, the primary bottleneck today is typically **generation quality and template adherence**, not retrieval. Investing in GraphRAG before exhausting simpler retrieval approaches risks building infrastructure for a problem you don't yet have.

This document frames the decision criteria, outlines the real complexity involved, and suggests a pragmatic path forward.

---

## 1. Authoring vs. Retrieval: Two Different Problems

| Concern | Authoring (your current focus) | Retrieval-heavy use cases |
|---|---|---|
| **Core task** | Generate new text that conforms to a template, regulatory style, and study-specific data | Find and synthesize information scattered across a large, heterogeneous corpus |
| **Context source** | Structured inputs (study data, prior sections, SAP, TLFs) — usually *known* and *bounded* | Unstructured corpus — user doesn't know where the answer lives |
| **Failure mode** | Wrong tone, hallucinated claims, template deviation | Missing context, incomplete retrieval, contradictory sources |
| **What fixes failures** | Better prompts, structured inputs, section-level validation | Better retrieval — hybrid search, re-ranking, graph traversal |

**Key insight**: When you're authoring Protocol sections from structured study data, you're doing *context assembly + generation*, not open-ended retrieval. The context window is your friend here — you already know which documents and data points feed each section.

GraphRAG shines when:
- A user asks "Which adverse events appeared across all Phase 3 studies for Drug X?" and the answer requires traversing relationships across 40+ CSRs, the IB, and PSURs.
- You need to reconcile conflicting information across document versions with temporal awareness.
- The retrieval query is implicit or multi-hop ("What safety signals should I carry forward from the PBRER into the next Protocol amendment?").

GraphRAG is overkill when:
- You're generating Section 6.1 of a Protocol and the inputs are the SAP, study design parameters, and a template.
- The document being authored draws from 2–5 known source documents that fit in context.
- Simple keyword/semantic search over a small corpus would surface the same information.

---

## 2. The Ontology Problem Is Real — and Underestimated

Your instinct about Phase 1 complexity is correct. This is the hardest part and the AWS toolkit doesn't solve it for you.

### 2.1 Clinical Documents Don't Share a Single Axis

```
Product level          Investigator Brochure, SmPC
   |
Study level            Protocol, CSR, ICF
   |
Product x Time         PBRER, PSUR, DSUR (temporal versioning)
   |
Submission level       CTD modules, ISS/ISE (cross-study aggregation)
```

A GraphRAG ontology needs to model:

- **Entities**: Drug/Product, Study, Site, Endpoint, Adverse Event, Population, Regulatory Submission, Document, Section, Version...
- **Relationships**: Drug → has_study → Study → has_endpoint → Endpoint; Study → reported_in → CSR; Drug → safety_profile_in → PBRER(v3); PBRER(v3) → supersedes → PBRER(v2)...
- **Temporal edges**: Version chains, reporting period boundaries, regulatory submission timelines
- **Cross-document references**: CSR Section 12 → references → Protocol Amendment 3 → modifies → Protocol v1.0

### 2.2 Schema Fragmentation vs. Monolithic Ontology

You face a fundamental design tension:

| Approach | Problem |
|---|---|
| **One schema per doc type** | No cross-document traversal (defeats the purpose of GraphRAG). Protocol graph can't reach into CSR graph. |
| **One shared ontology** | Massive upfront design effort. Every new doc type may require schema migration. Entity semantics differ across levels (a "population" in a Protocol vs. in an ISS means different things). |
| **Layered ontology** (pragmatic middle ground) | Core entities shared + doc-type-specific extensions. Still substantial design work, but more maintainable. Requires careful governance. |

None of these are quick to get right. The AWS GraphRAG toolkit handles the *infrastructure* (Neptune, embedding pipelines, graph queries) — but the ontology design, entity extraction prompt engineering, and relationship validation are 100% on you.

### 2.3 Entity Extraction Quality

LLM-based entity extraction from clinical documents is non-trivial:

- **Ambiguity**: "The primary endpoint" in a Protocol vs. a CSR may resolve to different things.
- **Coreference**: "Study 301", "the pivotal trial", "NCT12345678" all refer to the same entity.
- **Negation/Conditionality**: "If the patient discontinues..." vs. "The patient discontinued..." — both mention discontinuation but mean very different things.
- **Regulatory jargon density**: Clinical documents have high information density with domain-specific semantics.

You'd need substantial prompt engineering and validation pipelines to get extraction quality high enough for a production graph. With only 2–4 study IDs of Protocol data, you don't yet have enough volume to validate extraction quality or schema coverage.

---

## 3. The Pragmatic Progression

Rather than jumping to GraphRAG, consider this staged approach that lets retrieval needs *pull* you toward more complex solutions:

### Stage 0: Where You Are Now (Protocols, 2–4 studies)
- **Approach**: Direct context assembly. Study data + template + prior sections → LLM.
- **Retrieval**: Minimal. Source documents are known and bounded.
- **GraphRAG need**: None.

### Stage 1: ICF + CSR Pickup (next 2–3 months)
- **Approach**: Same direct assembly pattern. ICF draws from Protocol. CSR draws from Protocol + SAP + TLFs.
- **Retrieval**: May need to pull from related Protocol sections. Simple semantic search over the study's document set is likely sufficient.
- **GraphRAG need**: Unlikely. The document relationships are explicit and hierarchical (CSR → Protocol → SAP).
- **Signal to watch**: If the LLM frequently generates incorrect cross-references or misses context from related documents, that's a retrieval gap signal.

### Stage 2: Cross-Study Documents (PBRER, ISS/ISE)
- **Approach**: Now you're aggregating across studies. A PBRER needs safety data from *all* studies for a product over a reporting period.
- **Retrieval**: This is where simple search may start to fail. You need to find all AE mentions across 10+ CSRs, reconcile terminology, and track temporal changes.
- **GraphRAG need**: *Maybe*. This is the natural inflection point. But even here, a well-structured relational database with good metadata (study → document → section mapping) plus semantic search might suffice.
- **Decision point**: If you find yourself writing complex multi-join queries to assemble context and still missing things, that's when GraphRAG earns its keep.

### Stage 3: Full Platform (CTD modules, regulatory intelligence)
- **Approach**: True multi-document, multi-study, multi-product authoring and querying.
- **Retrieval**: Complex. Users may ask questions that span products, time periods, and document types.
- **GraphRAG need**: Strong. This is the use case GraphRAG was designed for.

**The key principle**: Let retrieval failures in production drive the decision, not speculative architecture.

---

## 4. How to Frame the Conversation

### What to say to the engineering client

> "We agree GraphRAG is the right long-term architecture for cross-document intelligence at scale. However, our current authoring use cases are generation-first, not retrieval-first — the source context for each document section is known and bounded.
>
> We propose deferring GraphRAG investment until we have:
> 1. **Sufficient document diversity** (ICF + CSR at minimum) to validate an ontology design
> 2. **Measurable retrieval gaps** — specific failure cases where vector search + metadata filtering can't surface the right context
> 3. **Cross-study use cases in scope** (PBRER, ISS/ISE) where multi-hop traversal becomes necessary
>
> In the meantime, we'll instrument our retrieval pipeline to log context assembly quality, so we have data to justify the GraphRAG investment when the time comes."

### Additional angles to consider

**1. POC scope creep risk**
A GraphRAG POC that only covers Protocols for 2–4 studies will show the technology "works" but won't validate the hard parts (ontology evolution, cross-document traversal, temporal versioning). There's a risk of building confidence in the solution without testing the actual pain points.

**2. Maintenance burden**
Every new document type potentially requires: new entity extraction prompts, schema extensions, re-ingestion of affected documents, and regression testing of existing queries. This is ongoing cost, not one-time.

**3. The "good enough" baseline**
Before GraphRAG, exhaust these simpler approaches:
- **Structured metadata + semantic search**: Tag chunks with study_id, doc_type, section_number, version. Filter before searching.
- **Parent-child retrieval**: Retrieve at chunk level, expand to section/document level for context.
- **Guided context assembly**: For authoring, explicitly define which source sections feed each target section (a dependency map, not a graph DB).

**4. What the AWS toolkit actually gives you**
The AWS GraphRAG toolkit provides Neptune integration, embedding pipelines, and hybrid retrieval infrastructure. It does *not* provide: ontology design, entity extraction prompts tuned to clinical documents, or document-type-specific relationship schemas. The hardest 70% of the work is still yours.

**5. Alternative: Lightweight knowledge structure**
If there's organizational pressure to "do something with graphs," consider a lightweight approach:
- Build a **document relationship map** (not a full knowledge graph) — just documents, sections, and explicit cross-references.
- Store in a simple graph or even a relational schema.
- Use it for *navigation and context assembly*, not for LLM retrieval.
- This is 10% of the effort and captures 60% of the structural value.

---

## 5. Decision Framework

| Question | If Yes → | If No → |
|---|---|---|
| Are users asking questions that span 5+ documents? | Consider GraphRAG | Semantic search is sufficient |
| Is the LLM frequently missing cross-references during authoring? | Retrieval gap — investigate | Current approach works |
| Do you have 3+ document types with cross-document relationships in production? | Ontology design becomes feasible | Too early to commit to a schema |
| Are you doing cross-study aggregation (PBRER, ISS/ISE)? | Strong GraphRAG signal | Stay with per-study context assembly |
| Can you enumerate which source sections feed each target section? | Guided assembly is sufficient | You may need discovery-based retrieval |

---

## 6. Bottom Line

Your framing is correct. GraphRAG is premature for your current scope. The strongest version of the argument is:

1. **Authoring ≠ retrieval**. Your immediate problem is generation quality from known inputs, not discovery across an unknown corpus.
2. **Ontology design is the hard part**, and you can't design it well without sufficient document type diversity and real cross-document use cases.
3. **A POC on 2–4 Protocol studies will validate infrastructure, not the actual hard problems** (schema evolution, cross-document traversal, temporal reasoning).
4. **There's a clear trigger point**: when ICF/CSR/PBRER authoring hits retrieval gaps that metadata-filtered semantic search can't solve, that's when GraphRAG earns its investment.

Instrument your current pipeline, ship ICF and CSR, and let the data tell you when it's time.
