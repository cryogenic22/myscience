# SPEC-009: The Rebirth — A Singular Product, Not a Collection of Features

*Author: Claude + Cryogenic · Date: 2026-03-29*
*Philosophy: Jony Ive — "Simplicity is not the absence of clutter; it is the creation of clarity."*

---

## 1. The Problem Is Not the CSS

The current frontend has 32 TSX components, 3 pages, a design token system, a graph renderer, a chat panel, a canvas, a data catalog, search with filters, entity previews, and a literature explorer. Every one of these works. None of them belong together.

The experience feels like walking through a house where every room was designed by a different architect. The kitchen is modern. The bedroom is Victorian. The bathroom is brutalist. Each room is competent — but the house has no soul.

This is not a CSS problem. This is not a "polish" problem. This is an **identity** problem.

The question is not "how do we fix the UI." The question is: **what is this product, expressed as a single sentence?**

---

## 2. What Market Zero Actually Is

Market Zero is a place where you see the invisible connections in pharmaceutical intelligence.

Not a chatbot. Not a dashboard. Not a search engine. Not a graph explorer. It is a **lens** — you look through it, and relationships that were hidden become visible. You ask a question, and the answer isn't text — it's structure. It's the shape of how drugs, targets, trials, companies, and mechanisms relate to each other.

Everything in the interface should serve this one idea: **making the invisible visible.**

---

## 3. The Diagnosis

### 3.1 What the Code Audit Revealed

I read every page, every component, every CSS rule. Here is what I found:

**Three styling paradigms fighting each other.** Tailwind utility classes for layout (`flex h-full flex-col`). CSS custom properties for colours (`var(--color-ink)`). Inline styles for everything else (`style={{ padding: '32px 28px', maxWidth: '680px' }}`). The LandingPage has zero CSS classes — every single element is styled inline, including hover states managed through `onMouseEnter` event handlers. The WorkspacePage delegates to child components that each choose their own approach. The result is a codebase where no two components look like they were written by the same person.

**Magic numbers everywhere.** The chat panel uses `maxWidth: '680px'`. The topbar is `52px`. The textarea caps at `120px`. The drawer clamps between `360px` and `640px`. The canvas panel header uses `16px 24px` padding while the chat uses `32px 28px`. None of these numbers come from a shared scale. They were chosen in isolation, and they create a subtle but pervasive sense of visual discord.

**The landing page is a brochure, not a doorway.** It has a hero section, a metrics strip, a pillar grid — all the artefacts of a marketing page. But Market Zero doesn't need to sell itself to the person who's already logged in. The landing page should be the moment you step into the workspace, not the moment you read about it.

**Dark mode is declared but broken.** The `html.dark` selector in `index.css` sets `--color-line` to `rgba(0,0,0,0.06)` — the same value as light mode. Lines disappear in dark mode because they're black-on-dark. The hook exists, the toggle exists, the variables exist, but no one has actually used the product in dark mode.

**The legacy compatibility layer tells the whole story.** Lines 606–727 of `index.css` are 120 lines of `!important` overrides mapping old Tailwind classes (`bg-white`, `bg-slate-50`, `text-slate-900`) to CSS variables. This is the archaeological record of a frontend that has been incrementally patched rather than coherently designed. Each layer of paint covers the previous one, but the surface is uneven.

**Chat and canvas are roommates, not partners.** They share a split panel but not a data model. When the chat mentions "semaglutide," the canvas doesn't highlight it. When you click a node in the graph, the chat doesn't know. They are two applications that happen to share a viewport. The `WorkspacePage` passes `onCanvasUpdate` callbacks but the integration is shallow — it passes pre-formatted data objects, not entity references.

### 3.2 The Maturity Taxonomy

The audit revealed issues at every level of a maturity hierarchy:

| Level | What It Means | Market Zero Status |
|-------|--------------|-------------------|
| **Foundation** | Consistent spacing, typography, colour | Partially there (tokens exist, usage is inconsistent) |
| **Components** | Reusable, stateful UI primitives | Weak (buttons are inline-styled, no shared component library) |
| **Composition** | Components combine into coherent views | Mixed (chat is well-composed, landing page is monolithic) |
| **Flow** | Views connect into a navigable experience | Broken (chat → graph → detail is three separate mental models) |
| **Identity** | The product feels like one thing | Missing (no unifying interaction paradigm) |

You cannot fix Level 5 (identity) by patching Level 1 (spacing). The incremental approach — fix this padding, add that hover state, consolidate these components — will produce a more polished version of a disconnected product. It will still feel like three tools sharing a screen.

---

## 4. Research: What the Best Products Do

I studied LinkedIn, Neo4j Bloom, Reltio, Spotify, Palantir Foundry, Notion, Figma, Perplexity, Observable, BenchSci, and Clarivate. The patterns that matter most:

### 4.1 The Graph Is the Stage (Neo4j Bloom)

In Bloom, the graph canvas is 80% of the viewport. Search, filters, properties — they're all supporting panels around the edges. You are *in* the graph. Everything you do happens in relation to what you see. The graph is not a feature — it is the product.

Market Zero currently gives the graph equal space with the chat. It's a side panel. A visualisation you can open. This is like Spotify putting the album art in a sidebar.

### 4.2 One Entity, One Card, Everywhere (LinkedIn)

LinkedIn rebuilt its profile system as configurable card components. A person, a company, a job — each has one canonical card that renders in feeds, search, profiles, and recommendations. The card adapts its density (compact in a list, expanded in a profile) but its identity is constant. You always recognise it.

Market Zero has no entity card system. A drug appears as a text mention in chat, a coloured circle in the graph, a row in the data catalog, and a detail panel in the canvas. These are four different visual identities for the same thing.

### 4.3 Every Answer Is Traceable (Perplexity)

Perplexity numbers its citations. Every claim links to a source. You can verify anything with one click. This builds trust, which is essential in pharma intelligence where decisions have consequences.

Market Zero's chat produces narrative text with citations, but the connection between what the LLM says and what the knowledge graph contains is opaque. When the chat says "semaglutide targets GLP-1R," there's no way to see the BINDS_TO edge that supports this claim.

### 4.4 The Inspector Pattern (Figma)

In Figma, you select an object and its properties appear in a persistent right panel. No modals. No navigation. You stay in context. The selection drives the panel, not the other way around.

Market Zero's canvas tabs (Summary/Data/Entities/Context) are static. They show whatever the last chat response produced, not what you're looking at in the graph. Selecting a node in the graph doesn't update the canvas.

### 4.5 Progressive Disclosure, Not Progressive Overwhelm (Spotify)

Spotify shows you an artist page: name, image, top songs, albums, related artists. Five sections, clear hierarchy, generous whitespace. If you want more, you scroll or click. The initial view is calm. The depth is infinite but the surface is simple.

Market Zero's workspace shows everything at once: chat messages, graph nodes, canvas tabs, follow-up suggestions, confidence warnings, citation links, entity type filters, edge category legends. There is no hierarchy of attention. Everything competes equally.

---

## 5. The Verdict: Rebuild

### Why Incremental Won't Work

The problems are not additive — they're structural. Consider what "fixing" the current UI would require:

1. Refactor LandingPage from inline styles to CSS classes (~200 style objects)
2. Create a shared button component and replace 12+ inline button implementations
3. Create entity card components and wire them into chat, graph, canvas, catalog
4. Unify the data model so graph selections drive chat context and vice versa
5. Rebuild the layout from equal-panels to graph-centric
6. Fix dark mode (every inline style that references a colour needs a dark variant)
7. Add the spacing scale and replace 50+ magic numbers
8. Add component states (hover, focus, active, disabled, loading, error) to every interactive element
9. Replace the landing page with a workspace entry point
10. Build the inspector pattern for entity selection

Steps 1–3 are refactoring. Steps 4–5 are architectural changes. Steps 6–10 are new features. Doing all of this incrementally — while keeping the existing UI functional, while maintaining the existing patterns where they've been partially adopted — is more work than starting fresh with a clear system. Every incremental change has to negotiate with the three existing paradigms. A fresh surface has to negotiate with none.

### Why Rebuild Will Work

The backend is excellent. The API layer is clean. The services (QueryEngine, LLMSynthesizer, CTXContextBuilder, GraphTraversal, HybridSearch) are well-factored and well-tested. 180 tests passing. The data model is sound. The connectors work. The domain pack is extensible.

The frontend is 32 TSX files and ~8,000 lines of code. It's not a massive codebase. A focused rebuild of the UI layer — same React 19, same TypeScript, same Vite, same API endpoints — with a coherent design system from day one is a 4–6 week effort that produces a fundamentally different product experience.

You keep:
- The API layer (`api.ts` — all type definitions and fetch functions)
- The hooks (`useTheme`, `useAnimatedNumber`, `useHealthStats`)
- The KnowledgeGraph renderer (just built, well-architected)
- The brand constants (`brand.ts`)

You rebuild:
- The page structure (one workspace, not three pages)
- The layout system (graph-centric, not equal-panels)
- The component library (from a design system, not ad hoc)
- The CSS foundation (one paradigm, not three)
- The entity card system (one entity, one card, everywhere)
- The chat-to-graph integration (shared data model)

### What Jony Ive Would Say

*"The goal isn't to make it look better. The goal is to remove everything that isn't essential until what remains is inevitable. When you look at the product, you shouldn't think 'that's a nice design.' You should think 'of course. What else would it be?'"*

Market Zero's inevitable form is this: you look at a knowledge graph. You ask it questions. It shows you answers as structure. Everything else — the chrome, the panels, the tabs, the toggles — either serves this or shouldn't exist.

---

## 6. The Design Principles

Before any code, the team needs to agree on five principles that govern every decision:

### Principle 1: The Graph Is the Product

The knowledge graph occupies the majority of the viewport. It is always visible. Chat, properties, search — these are lenses that adjust what the graph shows. They don't compete with it for attention. They serve it.

When a user asks "show me EGFR inhibitors," the graph responds. When a user clicks a node, the properties panel responds. When a user asks "compare these two drugs," the graph highlights both and the panel shows the comparison. One stage, many spotlights.

### Principle 2: One Entity, One Identity

A drug looks the same everywhere. Same colour. Same icon. Same card shape. Whether it appears as a node in the graph, an inline mention in chat, a row in search results, or a detail card in the inspector — it is instantly recognisable as the same thing. You learn the visual language once.

### Principle 3: Quiet Until Needed

Controls, filters, legends, settings — they exist, but they don't demand attention. They appear when relevant and recede when not. A filter panel slides in when you're searching. The edge legend appears when you hover near the graph's edge. The properties panel expands when you select a node. The default state is calm.

### Principle 4: Every Claim Is Provable

If the system says "semaglutide has 47 active trials," the number 47 is a link. Click it and you see all 47 trials. If the system says "Novo Nordisk owns semaglutide," the word "owns" is a link to the OWNS edge with its provenance, confidence score, and source. Trust is built through transparency, not assertion.

### Principle 5: Materiality

The interface should feel like it's made of something. Surfaces have weight. Cards cast shadows. Transitions have physics. The graph's nodes have mass — they settle under gravity, they resist being pulled, they bounce against each other. This isn't decoration. It's the sensation that you're interacting with real information, not rendering pixels.

---

## 7. The Architecture

### 7.1 One Page, Three Zones

```
┌─────────────────────────────────────────────────────────────┐
│  ◉ Market Zero          [🔍 Search...]          [⚙] [◐]   │  ← Toolbar (48px)
├────────────┬──────────────────────────────┬─────────────────┤
│            │                              │                 │
│  Dialogue  │                              │   Inspector     │
│            │                              │                 │
│  Messages  │        Knowledge Graph       │   Entity card   │
│  from chat │                              │   Properties    │
│  thread    │        The stage.            │   Relationships │
│            │        Always visible.       │   Evidence      │
│            │        Responds to           │   Actions       │
│            │        everything.           │                 │
│            │                              │   (Appears on   │
│            │                              │    selection)   │
│            │                              │                 │
│            │                              │                 │
├────────────┤                              ├─────────────────┤
│ ┌────────┐ │                              │                 │
│ │ Input  │ │                              │                 │
│ └────────┘ │                              │                 │
└────────────┴──────────────────────────────┴─────────────────┘
  ~280px              flexible (fill)             ~320px
  collapsible                                     appears on
                                                  selection
```

**Toolbar** (48px): Logo, search (global entity search, not page navigation), settings, theme toggle. That's it. No segmented navigation. No breadcrumbs. No tab bar. You're always in the same place.

**Dialogue** (~280px, collapsible): The conversation thread. Compact. Messages are short — the graph does the heavy lifting. Input at the bottom. This is a *command line for the graph*, not a chat application. It can collapse to an icon when the user prefers direct manipulation of the graph.

**Knowledge Graph** (fills remaining space): Force-directed graph. Dark canvas. Entity-coloured nodes. Confidence-weighted edges. Pan, zoom, select. This is the product. It breathes. Nodes drift gently when idle. They respond when you interact.

**Inspector** (~320px, appears on selection): When you select a node or edge in the graph (or click an entity mention in chat), the inspector slides in from the right. Entity card at the top. Properties below. Related entities. Evidence trail. Actions (explore neighbourhood, find paths, compare). When nothing is selected, this panel doesn't exist — the graph takes the full width.

### 7.2 The Interaction Loop

```
Ask  →  The graph responds  →  Select  →  Inspect  →  Refine  →  Ask again
         (nodes appear,         (click       (properties    (filter,
          highlight,             a node)      appear)        drill down)
          filter)
```

This is one loop, not three features. The chat doesn't produce text answers — it produces *graph states*. "Show me EGFR inhibitors" causes 47 nodes to appear. "Which are in Phase 3?" causes 35 to fade and 12 to brighten. "Compare osimertinib and gefitinib" causes two nodes to glow and a comparison card to appear in the inspector.

The chat is a voice interface for the graph. The inspector is a magnifying glass for the graph. The graph is the thing.

### 7.3 The Entity Card

One component. Used everywhere.

```
┌──────────────────────────────────┐
│  ● Semaglutide                   │  ← Entity colour dot + name
│  GLP-1 receptor agonist          │  ← Primary descriptor
│                                  │
│  Novo Nordisk · Approved · T2D   │  ← Metadata line (owner · status · indication)
│                                  │
│  ━━━━━━━━━━━━━━━━━━━━  92%      │  ← Confidence bar
│                                  │
│  47 trials · 12 mechanisms ·     │  ← Relationship counts
│  3 patents · 156 papers          │
└──────────────────────────────────┘
```

**Compact** (in chat, search results): Just the first two lines — colour dot, name, descriptor.
**Standard** (in graph hover, inspector summary): All five lines.
**Expanded** (in inspector detail): All five lines plus sections for trials, mechanisms, evidence, etc.

Same visual identity. Always the coloured dot. Always the name first. Always the descriptor second. You learn it once.

### 7.4 The Colour System

Everything derives from a minimal palette. No arbitrary colours. Every colour means something.

```css
:root {
  /* ── Surface ── */
  --surface-primary:    #ffffff;
  --surface-secondary:  #f8f9fa;
  --surface-elevated:   #ffffff;
  --surface-graph:      #0f172a;    /* The graph canvas — always dark */

  /* ── Text ── */
  --text-primary:       #1a1a2e;
  --text-secondary:     #6b7280;
  --text-tertiary:      #9ca3af;
  --text-inverse:       #f1f5f9;    /* On dark surfaces */

  /* ── Accent ── */
  --accent:             #2563eb;    /* Blue — the single brand colour */
  --accent-soft:        #dbeafe;

  /* ── Entity (semantic, not decorative) ── */
  --entity-drug:        #2563eb;    /* Blue — the protagonist */
  --entity-company:     #d97706;    /* Amber — ownership */
  --entity-trial:       #0d9488;    /* Teal — research */
  --entity-target:      #8b5cf6;    /* Violet — biology */
  --entity-mechanism:   #7c3aed;    /* Deep violet — science */
  --entity-literature:  #16a34a;    /* Green — evidence */
  --entity-ta:          #e11d48;    /* Rose — classification */
  --entity-safety:      #ef4444;    /* Red — danger */

  /* ── Confidence ── */
  --confidence-high:    #16a34a;    /* ≥0.8 */
  --confidence-mid:     #d97706;    /* 0.5–0.8 */
  --confidence-low:     #ef4444;    /* <0.5 */

  /* ── Spacing (4px grid) ── */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;

  /* ── Typography ── */
  --font-display:  'Fraunces', serif;
  --font-body:     'DM Sans', sans-serif;
  --font-mono:     'JetBrains Mono', monospace;

  --text-xs:   12px;
  --text-sm:   13px;
  --text-base: 15px;
  --text-lg:   17px;
  --text-xl:   20px;
  --text-2xl:  24px;
  --text-3xl:  30px;

  /* ── Radius ── */
  --radius-sm:   6px;
  --radius-md:   10px;
  --radius-lg:   16px;
  --radius-full: 9999px;

  /* ── Shadow ── */
  --shadow-sm:  0 1px 2px rgba(0,0,0,0.05);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg:  0 12px 32px rgba(0,0,0,0.12);

  /* ── Motion ── */
  --ease-out:   cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in:    cubic-bezier(0.7, 0, 0.84, 0);
  --duration-fast:   120ms;
  --duration-normal: 200ms;
  --duration-slow:   400ms;
}
```

**One paradigm**: CSS custom properties. Not Tailwind utilities for colours. Not inline hex values. Not rgba() magic numbers. Every colour, every spacing value, every font size comes from a token. If it's not a token, it doesn't belong.

### 7.5 Dark Mode (First-Class, Not Afterthought)

The graph canvas is *always* dark. The surrounding chrome adapts:

```css
html.dark {
  --surface-primary:    #0f172a;
  --surface-secondary:  #1e293b;
  --surface-elevated:   #1e293b;
  --text-primary:       #f1f5f9;
  --text-secondary:     #94a3b8;
  --text-tertiary:      #64748b;
  --shadow-sm:  0 1px 2px rgba(0,0,0,0.3);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg:  0 12px 32px rgba(0,0,0,0.5);
}
```

Because the graph is always dark, the transition between light and dark mode is gentle — only the chrome changes. The centre of the screen (where your eyes spend 80% of the time) is stable.

### 7.6 Typography as Architecture

Fraunces is the voice. It speaks only for the product name and section headers — rarely, and with authority. DM Sans is the workhorse. It carries every label, every message, every property value. The two fonts never compete.

```
Product name:     Fraunces 300   --text-xl    --text-secondary
Section headers:  Fraunces 400   --text-lg    --text-primary
Entity names:     DM Sans 600    --text-base  --text-primary
Body text:        DM Sans 400    --text-base  --text-primary
Metadata:         DM Sans 400    --text-sm    --text-secondary
Captions:         DM Sans 400    --text-xs    --text-tertiary
Code/IDs:         JetBrains Mono --text-xs    --text-tertiary
```

Six levels. No more. If you need a seventh, you've designed it wrong.

---

## 8. The Component Library

### 8.1 What Gets Built (and Nothing Else)

| Component | Purpose | Variants |
|-----------|---------|----------|
| `EntityDot` | Coloured dot indicating entity type | 8 entity colours, 3 sizes (sm/md/lg) |
| `EntityCard` | The universal entity representation | compact, standard, expanded |
| `EntityMention` | Inline clickable entity reference in text | with/without descriptor |
| `ConfidenceBar` | Visual confidence indicator | bar, dot, text |
| `Button` | Action trigger | primary, secondary, ghost, danger; sm, md |
| `Input` | Text entry | single-line, multi-line, search |
| `Panel` | Collapsible side panel | left (dialogue), right (inspector) |
| `Section` | Expandable content section within inspector | default open, default closed |
| `Badge` | Status indicator | approved, recruiting, completed, failed, etc. |
| `Tooltip` | Hover information | text, entity card |
| `EdgeLabel` | Link type indicator | coloured, with confidence |
| `CitationLink` | Numbered reference to evidence source | inline, footnote |

12 components. Not 32. Every component has documented states (default, hover, active, focus, disabled, loading). Every component uses only CSS custom properties. Every component has a dark mode that works.

### 8.2 What Gets Removed

These current components are symptoms of the disconnection problem and should not survive the rebuild:

- **LandingPage.tsx** — replaced by the workspace (you're always in the workspace)
- **ModernGraph.tsx** — already deprecated, delete
- **GraphMini.tsx** — re-export shim, delete (KnowledgeGraph replaces it)
- **DataCatalogPanel.tsx** — the catalog becomes a search mode, not a separate panel
- **LiteratureExplorer.tsx** — literature is an entity type in the graph, not a separate explorer
- **Pill.tsx** — replaced by Badge component
- **Drawer.tsx** — replaced by Panel component

### 8.3 What Gets Kept and Refined

- **KnowledgeGraph.tsx** — the renderer is well-built; extend with inspector integration
- **brand.ts** — entity type colours, labels, display names; expand with the full token system
- **api.ts** — the API layer is clean; keep the types, keep the fetch functions
- **useTheme.ts** — keep, fix dark mode CSS values
- **useAnimatedNumber.ts** — keep, useful for metric transitions
- **useHealthStats.ts** — keep, wire into workspace status

---

## 9. The Rebuild Plan

### Phase 0: Design System Foundation (Week 1)

**Deliverable**: A CSS file and a component storybook that define the entire visual language before any page is built.

1. Write `index.css` from scratch — tokens only, no legacy compatibility layer
2. Build the 12 components listed in §8.1 as pure, isolated units
3. Each component has: TypeScript props, CSS using only tokens, documented states
4. Verify dark mode for every component
5. Create a `/dev` route that renders all components for visual verification

**Jony Ive checkpoint**: *Can you look at the component storybook and feel that these belong together? Do they feel like they were carved from the same material?*

### Phase 1: The Workspace Shell (Week 2)

**Deliverable**: The three-zone layout with real graph rendering but stub data.

1. Build `Workspace.tsx` — the only page
2. Implement the three-zone layout: Dialogue | Graph | Inspector
3. Dialogue panel: collapsible, with message list and input
4. Inspector panel: appears on entity selection, slides from right
5. Graph canvas: KnowledgeGraph component, fills centre
6. Toolbar: logo, global search, settings, theme toggle
7. Wire `useTheme` for light/dark chrome switching
8. No API calls yet — use hardcoded sample graph data

**Jony Ive checkpoint**: *With sample data and no functionality, does the workspace feel like a place you want to be? Is it calm? Is the graph the thing your eyes go to first?*

### Phase 2: Chat → Graph Integration (Week 3)

**Deliverable**: Ask a question in the dialogue, see the graph respond.

1. Wire the chat API (`/chat` endpoint) to the dialogue panel
2. Parse entity mentions in responses → render as `EntityMention` components
3. When chat returns graph data (nodes/edges), update the KnowledgeGraph
4. Implement "graph states" — each chat response produces a graph configuration
5. Citation numbers in chat responses link to evidence in the inspector
6. Follow-up suggestions appear as compact buttons below messages

**Jony Ive checkpoint**: *When you ask "show me GLP-1 drugs" and the graph fills with blue nodes — does that feel like the system understood you? Is the response visual, not textual?*

### Phase 3: Inspector + Entity Cards (Week 4)

**Deliverable**: Click any entity in the graph or chat, see its full profile in the inspector.

1. Wire graph node selection → inspector panel
2. Build inspector sections: Identity, Properties, Relationships, Evidence, Actions
3. Implement `EntityCard` in all three variants (compact, standard, expanded)
4. Wire chat entity mentions → same inspector (click drug name in chat → inspector shows drug)
5. Inspector "Explore" action → expands the entity's neighbourhood in the graph
6. Inspector "Compare" action → selects two entities for side-by-side
7. Evidence section shows CitationLinks to papers, trials, with confidence scores

**Jony Ive checkpoint**: *When you select semaglutide in the graph and the inspector reveals its mechanism, its trials, its competitors — does it feel like you're holding the drug in your hand and turning it over to see every side?*

### Phase 4: Search + Discovery (Week 5)

**Deliverable**: Global search that feeds the graph and replaces the standalone catalog.

1. Global search in the toolbar → entity type-ahead (fuzzy match against all entity types)
2. Search results appear as a compact list overlaying the left edge of the graph
3. Selecting a result → centres the graph on that entity + opens inspector
4. "Browse by type" → shows entities of that type as a filterable list
5. Filters (entity type, confidence, date range) appear contextually
6. Remove standalone Data Catalog and Literature Explorer — their functionality lives in search + graph + inspector

**Jony Ive checkpoint**: *Is searching and browsing the same gesture as asking and exploring? There should be no mode switch. The search bar and the dialogue are two ways of doing the same thing.*

### Phase 5: Polish + Edge Cases (Week 6)

**Deliverable**: The product feels finished.

1. Responsive layout: on tablet, dialogue collapses to icon; on mobile, full-screen graph with bottom sheet for dialogue
2. Keyboard navigation: arrow keys traverse graph nodes, Enter opens inspector, Escape closes panels
3. Loading states: skeleton loaders for inspector, gentle pulse for graph while loading
4. Error states: inline, never modal, always recoverable
5. Empty states: when graph is empty, show a single centred prompt ("Ask a question or search for an entity")
6. Micro-animations: node entrance (scale from 0 → 1, 200ms ease-out), edge drawing (stroke-dashoffset animation), inspector slide (transform, 300ms ease-out)
7. Performance: virtualise large node counts (>500), debounce graph physics, lazy-load inspector sections
8. Accessibility: ARIA labels on graph nodes, focus management for panel transitions, reduced-motion support

**Jony Ive checkpoint**: *Use the product for 30 minutes. Does it ever surprise you? (It shouldn't.) Does it ever frustrate you? (It definitely shouldn't.) Does it feel like it's been here forever — like it was always this way?*

---

## 10. What We Don't Build

Equally important — things that would dilute the identity:

- **No dashboard page.** Dashboards are for products that don't know what to show you. The graph shows you what matters.
- **No settings page.** Preferences (theme, layout density) live in a popover from the toolbar. Not a page.
- **No onboarding tutorial.** If the product needs a tutorial, the product is wrong. The empty state should make the first action obvious.
- **No notification centre.** If something important happens (a data refresh, a new connection discovered), it appears as a subtle graph animation — a new node drifting in, a new edge drawing itself.
- **No tabs within the inspector.** Tabs create mode-switching. Sections with progressive disclosure (expand/collapse) keep you in one continuous scroll.

---

## 11. The Emotional Target

When a pharmaceutical analyst opens Market Zero, they should feel what an architect feels when they open a well-made drawing tool, or what a musician feels when they pick up a fine instrument.

Not impressed. Not overwhelmed. **Ready.**

The tool doesn't demand attention. It offers clarity. The graph is there, breathing gently, waiting. The input is there, empty, inviting. The space is calm, uncluttered, confident.

And then they type a question, and the graph comes alive, and the connections that were invisible become visible, and they think: *this is why I came here.*

That's the product.

---

## 12. Technical Migration Strategy

### What Stays (Backend)
- All Python services, API routes, database, connectors — untouched
- All 180+ tests — untouched
- The API contract (`/chat`, `/graph/traverse`, `/search`, `/entities`) — stable

### What Stays (Frontend)
- `api.ts` — type definitions and API client functions
- `brand.ts` — entity colours, labels (expanded with full token system)
- `KnowledgeGraph.tsx` — the canvas renderer (enhanced, not replaced)
- `hooks/useTheme.ts`, `hooks/useAnimatedNumber.ts`, `hooks/useHealthStats.ts`
- `vite.config.ts` — build configuration

### What Gets Rewritten
- `index.css` — from scratch, tokens only
- `App.tsx` — single route, single workspace
- `pages/` — one file: `Workspace.tsx`
- `components/layout/` — `Toolbar.tsx`, `DialoguePanel.tsx`, `InspectorPanel.tsx`
- `components/ui/` — the 12-component library from §8.1
- `components/chat/` — simplified: `MessageList.tsx`, `MessageInput.tsx`, `Message.tsx`
- `components/canvas/` — removed (the graph IS the canvas)

### What Gets Deleted
- `pages/LandingPage.tsx`
- `pages/WorkspacePage.tsx`
- `components/ModernGraph.tsx`
- `components/GraphMini.tsx`
- `components/DataCatalogPanel.tsx`
- `components/LiteratureExplorer.tsx`
- `components/ui/Drawer.tsx`
- `components/ui/Pill.tsx`
- `components/layout/WorkspaceLayout.tsx` (replaced by Workspace.tsx)
- `components/canvas/CanvasPanel.tsx` (replaced by InspectorPanel.tsx)
- `components/search/*` (rebuilt as part of Toolbar + graph integration)
- The legacy compatibility layer in `index.css` (lines 606–727)

### Line Count Estimate

| Current | Rebuilt |
|---------|--------|
| 32 TSX files, ~8,000 lines | ~18 TSX files, ~4,500 lines |
| 727 lines CSS (with 120 lines legacy overrides) | ~250 lines CSS (pure tokens + components) |
| 3 styling paradigms | 1 styling paradigm |

Fewer files. Fewer lines. One way of doing things. That's what maturity looks like.

---

## 13. Success Criteria

The rebuild is complete when:

| Criterion | Measure |
|-----------|---------|
| **One page** | There is exactly one route. You are always in the workspace. |
| **Graph-centric** | The graph occupies ≥55% of the viewport on desktop. |
| **Connected flow** | Asking a question in chat visibly changes the graph within 500ms. |
| **Entity identity** | The same drug looks the same in chat, graph, inspector, and search. |
| **Provenance** | Every factual claim in chat has a clickable citation linking to evidence. |
| **Zero magic numbers** | `grep -r 'px' src/` returns only CSS custom property definitions. |
| **One styling paradigm** | No Tailwind colour utilities. No inline colour values. CSS variables only. |
| **Dark mode works** | Every component is visually correct in both themes. |
| **Calm empty state** | With no data loaded, the workspace is inviting, not broken. |
| **5-second test** | A new user can identify what the product does within 5 seconds of seeing it. |

---

## 15. The Librarian's Lens — Data Stewardship Interface

### 15.1 The Second Persona

SPEC-009 §1–14 is designed for the **analyst** — the person who asks "what drugs compete with semaglutide?" and expects to see structure. But Market Zero has a second, equally critical persona: the **data librarian**.

The librarian doesn't ask "what competes with semaglutide?" They ask:

- "When did ClinicalTrials.gov last refresh?"
- "Why are 23% of drug records missing mechanism links?"
- "What did the steward fix overnight?"
- "Which entity resolution failures keep recurring?"
- "Is our ChEMBL coverage improving or degrading?"
- "Show me every quality signal above priority 0.7."

This persona already has extraordinary backend support:

| Backend Service | What It Does | API Surface |
|----------------|-------------|-------------|
| `DataSteward` | Autonomous curation loop: 20 iterations, deterministic-first enrichment | `POST /steward/run`, `/status`, `/actions` |
| `StewardSignalCollector` | Aggregates gaps from query telemetry, user feedback, quality metrics | `GET /steward/signals` |
| `FAIRScorer` | 5-dimension quality snapshot with trending | `GET /steward/status` |
| `DataQualityEngine` | Per-record scoring across 5 rule categories | Stored in `data_quality_results` |
| `EntityAgentOrchestrator` | Specialised agents per entity type (pricing, trial, drug, company) | `GET /steward/agents`, `POST .../run` |
| `FeedbackLoopOrchestrator` | Three closed loops: query patterns → weights, resolution failures → aliases, quality → prompts | `POST /steward/feedback-loops` |
| `DatasetCatalog` | 15 source profiles with Croissant metadata, freshness, field coverage | `GET /catalog/datasets` |
| `HITLReviewManager` | Unresolved entity queue for human-in-the-loop resolution | `GET /catalog/hitl/queue` |
| `InsightEngine` | Proactive intelligence signals (safety, pipeline, competitive) | `GET /steward/insights` |

The current frontend crams all of this into a `DataCatalogPanel` with four cramped tabs (Overview, Browse, Changes, Curation). Most of the steward infrastructure — signals, FAIR trending, entity agents, feedback loops, action history — has no UI at all. The librarian is flying blind.

### 15.2 Not a Second Page — A Second Lens

The solution is not a separate "admin page" or "data management dashboard." That would break the single-workspace principle. Instead, the workspace has **two lenses** — toggled by a single control in the toolbar.

```
┌─────────────────────────────────────────────────────────────┐
│  ◉ Market Zero    [🔍 Search...]    [◈ Explore ◆ Curate]   │
└─────────────────────────────────────────────────────────────┘
                                       ↑
                                  Lens toggle
```

**Explore** (default): The analyst's lens. The graph shows entities and their relationships. Chat asks questions. The inspector shows entity detail.

**Curate**: The librarian's lens. The graph shows the *data supply chain*. Chat becomes a steward command panel. The inspector shows quality metrics, signals, and actions.

Same three-zone layout. Same components. Different data, different purpose.

### 15.3 The Curate Lens — What Changes

#### The Graph Becomes a Supply Chain Map

In Curate mode, the graph canvas doesn't show drugs and companies. It shows **sources, entity types, and quality flows**:

```
     ┌──────────────┐
     │ ClinicalTrials│──→ [trial] ──→ ● 4,200 records
     │   .gov       │               quality: 0.82 ▲
     └──────────────┘               freshness: 3 days
           │
           ├─────────────→ [investigator] ──→ ● 1,100 records
           │                                  quality: 0.54 ▼
           │
     ┌──────────────┐
     │   PubMed     │──→ [literature] ──→ ● 8,900 records
     └──────────────┘                    quality: 0.91 ▲

     ┌──────────────┐
     │   ChEMBL     │──→ [molecular_target] ──→ ● 0 records ⚠
     └──────────────┘    (not yet wired)
```

Nodes are **sources** (left) and **entity types** (right). Edges show which source feeds which entity type. Node size reflects record count. Node colour reflects quality score (green ≥0.8, amber ≥0.5, red <0.5). A pulsing animation indicates a source that's currently refreshing. A warning icon flags stale or unwired sources.

This is still a graph — it uses the same KnowledgeGraph renderer, the same physics, the same pan/zoom. But the data is different. The librarian sees the shape of the data pipeline, not the shape of the pharma landscape.

#### The Dialogue Becomes the Steward Console

In Curate mode, the dialogue panel adapts:

- **Steward status**: a compact status bar at the top showing last run time, actions taken, signals pending
- **Quick actions**: "Run steward loop", "Refresh all sources", "Run quality scorecard" — as buttons, not typed commands
- **Signal feed**: the prioritised signal queue (from `StewardSignalCollector`) rendered as compact cards, newest first
- **Chat still works**: the librarian can ask "why are drug records missing mechanisms?" and the chat understands this is a data quality question, not an analytical one

The dialogue input placeholder changes from "Ask about the pharma landscape..." to "Ask about data quality, sources, or steward activity..."

#### The Inspector Becomes the Quality Dashboard

When the librarian selects a source node in the supply chain graph, the inspector shows:

```
┌──────────────────────────────────┐
│  ■ ClinicalTrials.gov            │  ← Source name
│  API · Nightly at 02:00 UTC      │  ← Collection method + schedule
│                                  │
│  Records: 4,247                  │
│  Last refresh: 3 hours ago       │
│  Quality: 0.82 ▲ (+0.03)        │
│                                  │
│  ── FAIR Scores ──               │
│  Completeness   ━━━━━━━━━━  87%  │
│  Link density   ━━━━━━━━━   82%  │
│  Source diversity ━━━━━━━   71%  │
│  Freshness      ━━━━━━━━━━━ 94%  │
│  Resolution     ━━━━━━━━━━  91%  │
│                                  │
│  ── Fields Collected ──          │
│  NCT ID · Title · Phase ·       │
│  Status · Sponsor · Conditions · │
│  Enrollment · Start date         │
│                                  │
│  ── Recent Steward Actions ──    │
│  ✓ Backfilled 47 TA links (2h)  │
│  ✓ Cleaned 12 sponsor names (4h)│
│  ✗ Dedup failed: lock held (6h) │
│                                  │
│  [Refresh Now]  [View Changes]   │
└──────────────────────────────────┘
```

When the librarian selects an **entity type** node:

```
┌──────────────────────────────────┐
│  ● Drug Entities                 │
│  10 entity types in domain pack  │
│                                  │
│  Total: 847 records              │
│  With embeddings: 812 (96%)      │
│  Avg quality: 0.78               │
│  Avg links/entity: 6.2           │
│                                  │
│  ── Quality Distribution ──      │
│  ■■■■■■■■■■  ≥0.8  (412)        │
│  ■■■■■■      0.5–0.8  (298)     │
│  ■■          <0.5  (137)         │
│                                  │
│  ── Top Gaps ──                  │
│  23% missing mechanism link      │
│  11% no brand_name               │
│  8% stale (>30 days)             │
│                                  │
│  ── Entity Agents ──             │
│  drug_agent: enabled, every 6h   │
│  Last run: 1h ago, 3 scripts ok  │
│                                  │
│  [Run Agent]  [Browse Entities]  │
└──────────────────────────────────┘
```

#### The HITL Review Queue

When signals or gaps are detected that require human judgement (entity deduplication candidates, ambiguous resolution matches), they appear in the signal feed with a "Review" action. Clicking "Review" opens a **review card** in the inspector:

```
┌──────────────────────────────────┐
│  ⚠ Resolution Conflict           │
│                                  │
│  "Novo Nordisk A/S" vs           │
│  "Novo Nordisk Inc"              │
│                                  │
│  Strategy: fuzzy_match (0.89)    │
│  Records: 147 vs 23              │
│                                  │
│  [Merge →] [Merge ←] [Keep Both]│
└──────────────────────────────────┘
```

This replaces the current cramped "Curation" tab with a proper review flow — one item at a time, clear actions, no cognitive overload.

### 15.4 The FAIR Trend Line

One element that should always be visible in Curate mode (regardless of what's selected): a compact **FAIR trend sparkline** in the toolbar area.

```
FAIR: 0.76 ▲  ╱╲╱╲╱─╱ (30d)
```

This is the data librarian's vital sign. It answers the most important question at a glance: "Is the knowledge graph getting better or worse?" The `FAIRScorer.trend()` endpoint already returns the last N snapshots — this just needs a sparkline.

### 15.5 Supply Chain Graph — Node and Edge Types

The supply chain graph reuses the same KnowledgeGraph renderer but with different node/edge semantics:

**Node types:**
| Type | Shape | Size | Colour Logic |
|------|-------|------|-------------|
| Source (connector) | Square | Fixed medium | Health check: green=healthy, red=unhealthy |
| Entity type | Circle | ∝ record count | Quality score: green ≥0.8, amber ≥0.5, red <0.5 |
| Steward action | Diamond | Small | Status: green=completed, red=failed, amber=running |

**Edge types:**
| Edge | Meaning | Style |
|------|---------|-------|
| Source → Entity type | "feeds" | Solid, width ∝ record count |
| Entity type → Entity type | "links to" (via LinkRules) | Dashed, labelled with link type |
| Steward action → Entity type | "acted on" | Thin, animated dash |

**Animations:**
- A source that's currently refreshing pulses gently
- A steward action that's running has an animated dash along its edge
- Newly created links flash briefly when the graph updates
- Stale sources (>14 days) have a slow, dim pulse

### 15.6 Curate Mode Components

These additional components are needed for the Curate lens:

| Component | Purpose |
|-----------|---------|
| `SourceCard` | Inspector card for a data source (metrics, fields, schedule, actions) |
| `EntityTypeCard` | Inspector card for an entity type (counts, quality distribution, gaps, agents) |
| `SignalCard` | Compact card for a steward signal (gap type, priority, entity, action) |
| `ReviewCard` | HITL review item with merge/keep/reject actions |
| `FAIRSparkline` | Compact 30-day FAIR trend with current score |
| `QualityBar` | Horizontal bar showing quality distribution (green/amber/red segments) |
| `ActionLog` | Scrollable list of recent steward actions with status badges |

These follow the same design system — same tokens, same typography, same states. They're just domain-specific compositions of the base components (EntityDot, Badge, ConfidenceBar, Section).

### 15.7 API Endpoints Already Available

No new backend work needed — the Curate lens is purely a frontend composition over existing APIs:

| View Element | API Endpoint | Already Exists? |
|-------------|-------------|:-:|
| Source nodes + health | `GET /catalog/datasets` | ✅ |
| Source detail | `GET /catalog/datasets/{key}/profile` | ✅ |
| Entity type counts | `GET /catalog/stats` | ✅ |
| FAIR scores + trend | `GET /steward/status` | ✅ |
| Signal queue | `GET /steward/signals` | ✅ |
| Steward actions | `GET /steward/actions` | ✅ |
| Entity agents | `GET /steward/agents` | ✅ |
| HITL review queue | `GET /catalog/hitl/queue` | ✅ |
| Feedback stats | `GET /feedback/stats` | ✅ |
| Change log | `GET /catalog/datasets/{key}/changes` | ✅ |
| Run steward | `POST /steward/run` | ✅ |
| Run agent | `POST /steward/agents/{name}/run` | ✅ |
| Refresh source | `POST /steward/refresh` | ✅ |
| Resolve entity | `POST /catalog/hitl/resolve` | ✅ |

14 endpoints, all built, all tested, zero UI exposure for most of them.

### 15.8 Implementation Phase (Week 5.5 — overlaps with Phase 5 Polish)

The Curate lens is built *after* the Explore lens is complete, using the same component library:

1. **Lens toggle** in Toolbar (Explore / Curate segmented control)
2. **Supply chain graph data adapter** — transforms `/catalog/datasets` + `/catalog/stats` into KnowledgeGraph-compatible nodes/edges
3. **SourceCard** and **EntityTypeCard** components for the inspector
4. **SignalCard** and **ActionLog** for the dialogue panel's signal feed
5. **ReviewCard** for HITL queue items
6. **FAIRSparkline** in the toolbar (always visible in Curate mode)
7. **Quick action buttons** in the dialogue panel header (Run Steward, Refresh All, Run Scorecard)
8. **Chat context switch** — when in Curate mode, chat prepends "You are a data quality assistant" to the system prompt so responses are stewardship-oriented

### 15.9 The Librarian's Loop

Just as the analyst has a loop (Ask → Graph responds → Select → Inspect → Refine → Ask again), the librarian has one too:

```
Monitor  →  The supply chain graph shows health at a glance
   ↓
Identify →  A red node or a high-priority signal catches attention
   ↓
Inspect  →  Click to see quality breakdown, gaps, recent actions
   ↓
Act      →  "Run steward on this source" / "Merge these entities" / "Refresh ChEMBL"
   ↓
Verify   →  FAIR trend updates, node colour changes, action log records outcome
   ↓
Monitor  →  Back to the overview, watching the system improve
```

The librarian doesn't type queries. They watch, intervene, verify. The interface should feel like a control room — calm, information-dense, always current — not like a chat application.

### 15.10 What This Replaces

The Curate lens replaces the current `DataCatalogPanel.tsx` entirely:

| Current (DataCatalogPanel) | Curate Lens |
|---|---|
| 4 tabs crammed into a side panel | Full workspace with graph + inspector |
| Overview: static text metrics | Supply chain graph with live node health |
| Browse: paginated entity table | Entity type nodes with count/quality, click to browse |
| Changes: flat change log | Action log in dialogue panel + per-source change history in inspector |
| Curation: HITL queue as a list | Review cards with clear merge/keep/reject actions |
| No FAIR visibility | FAIR sparkline always visible |
| No signal queue | Signal feed in dialogue panel |
| No steward controls | Quick actions + agent management in inspector |
| No source health monitoring | Source nodes with health/freshness/quality indicators |

---

## 16. Revised Success Criteria

| Criterion | Measure |
|-----------|---------|
| **One page, two lenses** | Explore and Curate share the same workspace, toggled by one control. |
| **Graph-centric (both lenses)** | Explore: entity graph. Curate: supply chain graph. Both ≥55% viewport. |
| **Connected flow** | Asking a question in chat visibly changes the graph within 500ms. |
| **Entity identity** | The same drug looks the same in chat, graph, inspector, and search. |
| **Provenance** | Every factual claim in chat has a clickable citation linking to evidence. |
| **Zero magic numbers** | `grep -r 'px' src/` returns only CSS custom property definitions. |
| **One styling paradigm** | No Tailwind colour utilities. No inline colour values. CSS variables only. |
| **Dark mode works** | Every component is visually correct in both themes. |
| **Calm empty state** | With no data loaded, the workspace is inviting, not broken. |
| **5-second test** | A new user can identify what the product does within 5 seconds of seeing it. |
| **Librarian coverage** | All 14 steward/catalog API endpoints surfaced in the Curate lens. |
| **FAIR always visible** | The FAIR trend sparkline is always visible in Curate mode. |
| **HITL flow** | Entity resolution conflicts resolvable in ≤3 clicks. |

---

## 17. Files Modified by This Spec

### New Files — Explore Lens (Analyst)
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/components/layout/Toolbar.tsx`
- `frontend/src/components/layout/DialoguePanel.tsx`
- `frontend/src/components/layout/InspectorPanel.tsx`
- `frontend/src/components/ui/EntityDot.tsx`
- `frontend/src/components/ui/EntityCard.tsx`
- `frontend/src/components/ui/EntityMention.tsx`
- `frontend/src/components/ui/ConfidenceBar.tsx`
- `frontend/src/components/ui/Button.tsx`
- `frontend/src/components/ui/Input.tsx`
- `frontend/src/components/ui/Panel.tsx`
- `frontend/src/components/ui/Section.tsx`
- `frontend/src/components/ui/Badge.tsx`
- `frontend/src/components/ui/EdgeLabel.tsx`
- `frontend/src/components/ui/CitationLink.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/chat/Message.tsx`

### New Files — Curate Lens (Data Librarian)
- `frontend/src/components/curate/SourceCard.tsx`
- `frontend/src/components/curate/EntityTypeCard.tsx`
- `frontend/src/components/curate/SignalCard.tsx`
- `frontend/src/components/curate/ReviewCard.tsx`
- `frontend/src/components/curate/ActionLog.tsx`
- `frontend/src/components/curate/FAIRSparkline.tsx`
- `frontend/src/components/curate/QualityBar.tsx`
- `frontend/src/components/curate/SupplyChainAdapter.ts` — transforms catalog API data → KnowledgeGraph nodes/edges

### Deleted Files
- `frontend/src/pages/LandingPage.tsx`
- `frontend/src/pages/WorkspacePage.tsx`
- `frontend/src/components/ModernGraph.tsx`
- `frontend/src/components/GraphMini.tsx`
- `frontend/src/components/GraphExplorer.tsx`
- `frontend/src/components/DataCatalogPanel.tsx`
- `frontend/src/components/LiteratureExplorer.tsx`
- `frontend/src/components/ChatMessage.tsx`
- `frontend/src/components/ui/Drawer.tsx`
- `frontend/src/components/ui/Pill.tsx`
- `frontend/src/components/layout/WorkspaceLayout.tsx`
- `frontend/src/components/canvas/CanvasPanel.tsx`

### Rewritten
- `frontend/src/index.css` — from scratch
- `frontend/src/App.tsx` — single route
- `frontend/src/brand.ts` — expanded with full token system
- `frontend/src/components/KnowledgeGraph.tsx` — enhanced with inspector integration
