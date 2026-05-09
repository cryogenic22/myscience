✓ Signed off by Antigravity

# SPEC_022: Phase F Cockpit Design System

## Goal
Implement a next-generation "Cockpit" aesthetic for Market Zero that matches or exceeds the sophistication of Oura Ring, Apple Health, Apple.com, and Spotify. The new UI will feel extremely premium, responsive, and data-dense yet elegant.

## Design Tokens (Light & Dark Variants)

We will use CSS custom properties via `@theme` to manage colors dynamically.

### Dark Theme (North Star)
- **Backgrounds**: Deep, rich blacks and dark slate (`#0d1117`, `#161b22`, `#30363d`).
- **Surface Elevation**: Achieved via subtle lighter borders (`#21262d`) and minimal glowing drop-shadows instead of stark borders.
- **Accents**: 
  - Vibrant blue (`#58a6ff`) for primary actions.
  - Contextual semantics: Green (`#3fb950`) for positive signals, Amber (`#f0883e`) for warnings/overdue, Red (`#f85149`) for critical threats.

### Light Theme
- **Backgrounds**: Warm off-whites (`#fafaf8`, `#f5f5f3`) transitioning cleanly.
- **Surface Elevation**: White (`#ffffff`) surfaces with ultra-soft Apple-style shadows (`rgba(0,0,0,0.06)`).
- **Accents**: 
  - Core brand blue (`#1c6ef7`).

## Motion Principles
We will use **Framer Motion** for all significant layout transitions and micro-animations.
- **Why Framer Motion?** It handles complex presence (mounting/unmounting), layout shifts (shared element transitions), and physics-based spring animations natively in React, which CSS alone struggles with. The codebase already has `"framer-motion": "^12.34.2"` installed.
- **Micro-interactions**: 
  - Hover states: Subtle `translateY(-2px)` with shadow bloom.
  - Loading: Pulse animations (`0.4` to `1.0` opacity).
  - Page entry: Smooth `fade-up` (Y-axis translate + opacity).

## Typography Hierarchy
- **Display**: Syne (Weights 700/800) for grand headers (e.g., "GLP-1 WAR ROOM").
- **Body**: DM Sans for standard prose and UI labels.
- **Technical/Numeric**: DM Mono for scores, IDs, telemetry, and compact tabular data.
- **Micro**: Small uppercase tracking text (10px-11px, `letter-spacing: 0.05em`) for metadata and tags.

## Component Primitives Needed

1. **MetricRing**: Circular SVG progress indicators with gradient strokes for calibration scores.
2. **Sparkline**: Minimalist SVG line charts for trend visualization over time.
3. **RadarChart**: Hexagonal or circular radar charts for comparing entity attributes (e.g., in dossiers).
4. **FlowDiagram**: SVG-based node-edge visualization for event sequences (e.g., trial readouts leading to market shifts).
5. **Timeline**: Vertical chronological event list with branded nodes.
6. **AgentStatusBar**: Live telemetry ticker indicating background agentic loops and intelligence gathering.
7. **HeroCard**: Elevated featured components (e.g., top threat) with glow effects.
8. **ProvenanceTrail**: Visual breadcrumbs showing the AI's reasoning path from source document to synthesized insight.

## Phased Implementation Plan

Per alignment with the Backend Team and the CI Reimagined Spec, the frontend rollout will be strictly sequenced to ship buildable features first and defer backend-blocked surfaces.

- **Phase 1**: Setup & Primitives (Current PR). Introduce Framer Motion, update `index.css` with tokens. Build reusable primitives (`MetricRing`, `Sparkline`, `HeroCard`, `Timeline`).
- **Phase 2**: Sensing Feed Redesign (PR 2). Replace the default `InboxTab` surface with the new Sensing Feed (Always-On Sensing Mode), pulling from existing signal APIs.
- **Phase 3**: Confidence & Evidence Primitives (PR 3). Build the `ProvenanceTrail` and explicit confidence bands. Sprinkle these across all existing surfaces to make uncertainty a first-class visual.
- **Phase 4**: Disagreement Surface (PR 4). Implement the pattern for surfacing conflicting agent/source reads, allowing user resolution.

> [!WARNING]
> **Deferred Surfaces (Blocked on Backend Data Contracts)**
> Do NOT start on **Decision Workspace (5-panel)**, **War-Room mode**, **Source Health admin**, or **Ask-Anything overlay** until the relevant `SPEC_NNN` backend data contracts land on `main`.

## Accessibility Requirements
- **Lighthouse Score**: A11y ≥95 across all changed surfaces.
- **Keyboard Navigation**: Ensure logical tab order, especially within complex visualizations like `FlowDiagram`.
- **Focus Management**: Visible focus rings (`box-shadow: 0 0 0 3px rgba(88,166,255,0.15)`) for all interactive elements.
- **Contrast**: Ensure all text passes WCAG AA contrast ratios, particularly in dark mode against `#161b22`.

## Feature Flag Rollout
All new Phase F components will be wrapped or toggled conditionally using:
`localStorage.mz_ui_v2 === 'true'`
This ensures the legacy UI remains fully functional while the Cockpit is built progressively.
