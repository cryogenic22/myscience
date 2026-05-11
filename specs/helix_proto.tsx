import { useState, useEffect, useMemo } from "react";

// ─── THEMES ─────────────────────────────────────────────────────
const THEMES = {
  dark: {
    bg: "#08090c", surface: "#0f1115", surfaceAlt: "#15181f", border: "#1f2329",
    text: "#e8eaed", textDim: "#8a8f99", textFaint: "#4a4f59",
    accent: "#5eead4", accent2: "#a78bfa", danger: "#f87171", warn: "#fbbf24", ok: "#34d399",
  },
  light: {
    bg: "#fafafa", surface: "#ffffff", surfaceAlt: "#f3f4f6", border: "#e5e7eb",
    text: "#111827", textDim: "#6b7280", textFaint: "#9ca3af",
    accent: "#0d9488", accent2: "#7c3aed", danger: "#dc2626", warn: "#d97706", ok: "#059669",
  },
  hybrid: {
    bg: "#08090c", surface: "#0f1115", surfaceAlt: "#15181f", border: "#1f2329",
    text: "#e8eaed", textDim: "#8a8f99", textFaint: "#4a4f59",
    accent: "#5eead4", accent2: "#a78bfa", danger: "#f87171", warn: "#fbbf24", ok: "#34d399",
  },
};

// ─── TAXONOMY (from MarketZero) ─────────────────────────────────
const IMPACT_CATEGORIES = [
  { id: "financial", label: "Financial", color: "#60a5fa" },
  { id: "governance", label: "Governance", color: "#94a3b8" },
  { id: "strategic", label: "Strategic", color: "#a78bfa" },
  { id: "clinical", label: "Clinical", color: "#5eead4" },
  { id: "product", label: "Product", color: "#fb923c" },
  { id: "regulatory", label: "Regulatory", color: "#fbbf24" },
  { id: "ma", label: "M&A", color: "#f472b6" },
  { id: "access", label: "Pricing & Access", color: "#34d399" },
  { id: "ai", label: "AI & Digital", color: "#818cf8" },
  { id: "esg", label: "ESG & Supply", color: "#fb7185" },
];

const SOURCE_STREAMS = {
  trials: "Trials", regulatory: "Regulatory", publications: "Publications",
  payer: "Payer", kol: "KOL", financial: "Financial", patent: "Patent", internal: "Internal",
};

// ─── COMPANIES ──────────────────────────────────────────────────
const COMPANIES = [
  { id: "novo", name: "Novo Nordisk", short: "NOVO", color: "#003b71", role: "player" },
  { id: "lilly", name: "Eli Lilly", short: "LLY", color: "#d52b1e", role: "rival" },
  { id: "amgen", name: "Amgen", short: "AMGN", color: "#0063c3", role: "rival" },
  { id: "pfizer", name: "Pfizer", short: "PFE", color: "#0093d0", role: "rival" },
];

// ─── DEMO SIGNALS (with MZ taxonomy) ────────────────────────────
const SEED_SIGNALS = [
  { id: "s1", ts: 0.2, tier: 1, materiality: 9.1, category: "clinical", stream: "trials", company: "lilly",
    title: "SURMOUNT-MMO interim hit cardiovascular endpoint",
    source: "NCT05822830", detail: "Tirzepatide reduced MACE 38% vs placebo in obesity cohort. Lilly expected to file sNDA expansion.",
    fresh: true },
  { id: "s2", ts: 0.8, tier: 2, materiality: 6.8, category: "regulatory", stream: "regulatory", company: "amgen",
    title: "FDA Type B meeting granted on MariTide",
    source: "FDA-2025-N-2847", detail: "Amgen secured pre-NDA alignment for MariTide monthly dosing. Filing expected H2 2026." },
  { id: "s3", ts: 1.4, tier: 1, materiality: 8.2, category: "access", stream: "payer", company: "—",
    title: "Express Scripts adds 22% rebate floor for GLP-1s",
    source: "ESI 2026 formulary memo", detail: "All GLP-1 contracts must hit minimum 22% net discount or move to NDC-block. Affects 18M lives." },
  { id: "s4", ts: 2.1, tier: 2, materiality: 5.9, category: "clinical", stream: "publications", company: "pfizer",
    title: "Danuglipron oral bioavailability data published",
    source: "PMID:38291842", detail: "Phase 2 PK shows 8-12% bioavailability in fed state, half-life of 14h." },
  { id: "s5", ts: 2.9, tier: 2, materiality: 6.4, category: "strategic", stream: "kol", company: "lilly",
    title: "Dr. Aronne at AACE: 'orforglipron is the form factor that wins'",
    source: "AACE 2026 plenary", detail: "Influential KOL signals oral preference will drive prescriber adoption faster than expected." },
  { id: "s6", ts: 3.6, tier: 2, materiality: 5.2, category: "product", stream: "financial", company: "novo",
    title: "Wegovy Q3 supply guidance revised down 8%",
    source: "Internal S&OP", detail: "Continued constraint on US semaglutide API. Affects ability to capture new starts." },
  { id: "s7", ts: 4.3, tier: 3, materiality: 3.4, category: "clinical", stream: "trials", company: "novo",
    title: "CagriSema Phase 3 enrollment 94% complete",
    source: "NCT05669014", detail: "On track for H2 2026 readout." },
  { id: "s8", ts: 5.0, tier: 3, materiality: 3.8, category: "strategic", stream: "patent", company: "lilly",
    title: "Lilly granted CN composition patent on retatrutide salts",
    source: "WO2026/041287", detail: "Strengthens IP moat in China for triple agonist." },
  { id: "s9", ts: 5.8, tier: 2, materiality: 5.6, category: "product", stream: "internal", company: "novo",
    title: "MSL feedback: cardiologists asking for CV outcomes data",
    source: "Q3 MSL aggregated", detail: "Strong unmet need on Wegovy CV positioning. Action: accelerate SELECT subgroup pubs." },
  { id: "s10", ts: 6.5, tier: 1, materiality: 9.4, category: "regulatory", stream: "regulatory", company: "—",
    title: "CMS draft NCD on GLP-1 for CV indication out for comment",
    source: "CMS-1234-PCD", detail: "If finalized as written, Medicare covers GLP-1 for CV risk reduction starting 2027. ~$14B TAM unlock." },
];

// ─── DEMO MOMENTS ───────────────────────────────────────────────
const SEED_MOMENTS = [
  { id: "m1", priority: 1, ev_at_stake_musd: 340, expires_hours: 72,
    title: "Lilly orforglipron acceleration changes your pricing posture",
    summary: "Three signals jointly raise P(Lilly launches oral GLP-1 by Q1 '27) from 18% → 41%.",
    delta_belief: { from: 0.18, to: 0.41, label: "P(Lilly oral by Q1 '27)" },
    signal_chain: ["s1", "s5", "s8"], category: "strategic",
    plays: [
      { id: "p1a", label: "Defend with semaglutide oral acceleration", ev: 380, ev_var: 90, prob_success: 0.62, kind: "aggressive" },
      { id: "p1b", label: "Pivot pricing to capture share before launch", ev: 210, ev_var: 50, prob_success: 0.74, kind: "balanced" },
      { id: "p1c", label: "Hold and differentiate on CV outcomes", ev: 140, ev_var: 40, prob_success: 0.81, kind: "cautious" },
    ],
  },
  { id: "m2", priority: 2, ev_at_stake_musd: 1400, expires_hours: 456,
    title: "CMS NCD comment period closes in 19 days",
    summary: "Draft CV indication NCD opens ~$14B TAM. Your comment letter shapes the final scope.",
    delta_belief: { from: 0.35, to: 0.71, label: "P(NCD finalized Q1 '27)" },
    signal_chain: ["s10", "s1", "s9"], category: "regulatory",
    plays: [
      { id: "p2a", label: "Aggressive comment claiming broad CV scope", ev: 920, ev_var: 280, prob_success: 0.55, kind: "aggressive" },
      { id: "p2b", label: "Coalition comment with cardiology societies", ev: 740, ev_var: 140, prob_success: 0.78, kind: "balanced" },
      { id: "p2c", label: "Narrow technical comment on label specifics", ev: 410, ev_var: 80, prob_success: 0.88, kind: "cautious" },
    ],
  },
  { id: "m3", priority: 3, ev_at_stake_musd: 95, expires_hours: 168,
    title: "Express Scripts rebate floor: pre-emptive action window",
    summary: "22% rebate floor forces a posture decision in next 6 weeks.",
    delta_belief: { from: 0.50, to: 0.88, label: "P(ESI enforces uniformly)" },
    signal_chain: ["s3"], category: "access",
    plays: [
      { id: "p3a", label: "Match floor, accept margin compression", ev: -45, ev_var: 15, prob_success: 0.92, kind: "cautious" },
      { id: "p3b", label: "Negotiate carve-out for obesity-only", ev: 78, ev_var: 35, prob_success: 0.51, kind: "balanced" },
      { id: "p3c", label: "Walk from ESI Tier 2", ev: 140, ev_var: 110, prob_success: 0.28, kind: "aggressive" },
    ],
  },
];

// ─── WATCHLISTS ─────────────────────────────────────────────────
const SEED_WATCHLISTS = [
  { id: "w1", name: "Lilly GLP-1 pipeline", filter: "company:lilly + clinical OR regulatory", lastHit: "2h ago", active: 8, color: "#d52b1e" },
  { id: "w2", name: "ESI rebate enforcement", filter: "company:* + pricing & access + tier:1-2", lastHit: "1d ago", active: 3, color: "#34d399" },
  { id: "w3", name: "CMS NCD developments", filter: "regulatory + keyword:NCD OR CMS", lastHit: "4h ago", active: 12, color: "#fbbf24" },
  { id: "w4", name: "My internal MSL feed", filter: "stream:internal", lastHit: "6h ago", active: 4, color: "#a78bfa" },
];

// ─── DECISION LEDGER ────────────────────────────────────────────
const SEED_DECISIONS = [
  { id: "d1", date: "2026-04-12", title: "Match ESI floor with carve-out negotiation", class: "access", ev_at_stake: 95, committedBy: "J. Singh", outcome: "Pending", evidence: ["s3"] },
  { id: "d2", date: "2026-04-08", title: "File coalition NCD comment with cardiology societies", class: "regulatory", ev_at_stake: 740, committedBy: "Committee", outcome: "In progress", evidence: ["s10", "s9"] },
  { id: "d3", date: "2026-03-29", title: "Hold semaglutide oral acceleration", class: "strategic", ev_at_stake: 180, committedBy: "M. Chen", outcome: "Confirmed (Lilly delayed)", evidence: ["s5", "s1"] },
];

// ─── REVIEWER OBSERVATIONS ──────────────────────────────────────
const REVIEWER_OBSERVATIONS = [
  { id: "r1", week: "this week", kind: "pattern", text: "Your last 3 commits in Pricing & Access were Cautious-tier plays. Moments offered Balanced or Aggressive options with higher EV. Consider whether risk tolerance calibration warrants attention.", severity: "advisory" },
  { id: "r2", week: "this week", kind: "track-record", text: "Your decisions outperformed system-suggested alternatives in 7 of last 12 cases (58%). System accuracy on accepted recommendations: 78%.", severity: "info" },
  { id: "r3", week: "last week", kind: "lesson", text: "March 29 decision to hold oral acceleration was confirmed by Lilly's subsequent delay. Pattern: signals from KOL stream + patent stream jointly more predictive than either alone.", severity: "positive" },
];

// ─── AGENT ROSTER ───────────────────────────────────────────────
const AGENT_ROSTER = [
  { id: "a1", name: "Sentinel/Trials", role: "Sentinel", scope: "ClinicalTrials.gov, EU CTR", autonomy: 4, accuracy: 0.91, status: "watching", activity: "Monitoring 84 active trials", calls_today: 412 },
  { id: "a2", name: "Sentinel/Regulatory", role: "Sentinel", scope: "FDA, EMA, CMS, NICE", autonomy: 3, accuracy: 0.88, status: "watching", activity: "Tracking 12 dockets, 3 ad-coms", calls_today: 89 },
  { id: "a3", name: "Sentinel/Payer", role: "Sentinel", scope: "PBM formularies, payer policies", autonomy: 3, accuracy: 0.84, status: "watching", activity: "Indexed 47 formulary changes this week", calls_today: 156 },
  { id: "a4", name: "Sentinel/KOL", role: "Sentinel", scope: "Conferences, social, podcasts", autonomy: 2, accuracy: 0.76, status: "watching", activity: "Tracking 240 KOLs, AACE/EASD live", calls_today: 1894 },
  { id: "a5", name: "Synthesizer/Causal", role: "Synthesizer", scope: "Cross-stream signal fusion", autonomy: 4, accuracy: 0.83, status: "active", activity: "Generated 3 moments in 72h, 11 hypotheses", calls_today: 47 },
  { id: "a6", name: "Twin/Market State", role: "Twin", scope: "GLP-1 obesity & T2D twin", autonomy: 5, accuracy: 0.79, status: "updating", activity: "Posterior updated 6× today", calls_today: 23 },
  { id: "a7", name: "Strategist/Aggressive", role: "Strategist", scope: "War game persona", autonomy: 3, accuracy: 0.71, status: "idle", activity: "Last play: defend semaglutide acceleration", calls_today: 14 },
  { id: "a8", name: "Strategist/Balanced", role: "Strategist", scope: "War game persona", autonomy: 3, accuracy: 0.82, status: "idle", activity: "Last play: coalition NCD comment", calls_today: 14 },
  { id: "a9", name: "Strategist/Contrarian", role: "Strategist", scope: "War game persona", autonomy: 2, accuracy: 0.67, status: "idle", activity: "Last play: exit ESI Tier 2", calls_today: 14 },
  { id: "a10", name: "Executor/MSL Brief", role: "Executor", scope: "Auto-brief MSLs", autonomy: 4, accuracy: 0.94, status: "active", activity: "Drafted 7 briefs awaiting review", calls_today: 38 },
  { id: "a11", name: "Coach/Decision", role: "Coach", scope: "Watches decision patterns", autonomy: 2, accuracy: 0.74, status: "watching", activity: "Flagged 2 anchoring biases this quarter", calls_today: 4 },
];

// ─── MAIN APP ───────────────────────────────────────────────────
export default function App() {
  const [themeMode, setThemeMode] = useState("hybrid");
  const [view, setView] = useState("bridge");
  const [bridgeMode, setBridgeMode] = useState("live"); // live | digest_today | digest_week
  const [activeMoment, setActiveMoment] = useState(null);
  const [activeFrame, setActiveFrame] = useState(null); // Decision Frame modal
  const [decisionsOpen, setDecisionsOpen] = useState(false);
  const [signals] = useState(SEED_SIGNALS);
  const [now, setNow] = useState(Date.now());
  const [twinPulse, setTwinPulse] = useState(0);

  const theme = THEMES[themeMode];

  useEffect(() => {
    const i = setInterval(() => { setNow(Date.now()); setTwinPulse(p => p + 1); }, 2400);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: theme.bg, color: theme.text, fontFamily: "'Inter', system-ui, sans-serif", display: "flex" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&family=Instrument+Serif&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { -webkit-font-smoothing: antialiased; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${theme.border}; border-radius: 3px; }
        @keyframes pulse-soft { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
        @keyframes pulse-ring { 0% { transform: scale(1); opacity: 0.7; } 100% { transform: scale(2.5); opacity: 0; } }
        @keyframes fade-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slide-right { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .fade-up { animation: fade-up 0.4s ease forwards; }
        .fade-in { animation: fade-in 0.5s ease forwards; }
        .slide-right { animation: slide-right 0.25s ease forwards; }
        .pulse-soft { animation: pulse-soft 2s ease-in-out infinite; }
        .pulse-dot::after { content: ''; position: absolute; inset: 0; border-radius: 50%; background: inherit; animation: pulse-ring 1.8s ease-out infinite; }
        .nav-item:hover { background: ${theme.surfaceAlt} !important; color: ${theme.text} !important; }
      `}</style>

      {/* LEFT SIDEBAR NAV */}
      <Sidebar theme={theme} view={view} setView={setView} />

      {/* MAIN CONTENT */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <Header theme={theme} themeMode={themeMode} setThemeMode={setThemeMode}
          decisionsOpen={decisionsOpen} setDecisionsOpen={setDecisionsOpen} now={now} />

        <div style={{ flex: 1, overflow: "auto" }}>
          {view === "bridge" && (
            <Bridge theme={theme} signals={signals} moments={SEED_MOMENTS}
              openMoment={setActiveMoment} openFrame={setActiveFrame}
              twinPulse={twinPulse} bridgeMode={bridgeMode} setBridgeMode={setBridgeMode} />
          )}
          {view === "watchlist" && <WatchlistView theme={theme} />}
          {view === "kbq" && <KBQStub theme={theme} />}
          {view === "wargame" && <WarGameStub theme={theme} />}
          {view === "knowledge" && <KnowledgeStub theme={theme} />}
          {view === "replay" && <ReplayStub theme={theme} />}
          {view === "reviewer" && <ReviewerView theme={theme} />}
          {view === "agents" && <AgentsView theme={theme} />}
          {view === "connectors" && <ConnectorsView theme={theme} />}
        </div>
      </div>

      {/* MODALS / OVERLAYS */}
      {activeMoment && <MomentView theme={theme} themeMode={themeMode}
        moment={activeMoment} signals={signals} close={() => setActiveMoment(null)} />}
      {activeFrame && <DecisionFrameModal theme={theme} signal={activeFrame}
        close={() => setActiveFrame(null)} />}
      {decisionsOpen && <DecisionLedgerPanel theme={theme} close={() => setDecisionsOpen(false)} />}
    </div>
  );
}

// ─── SIDEBAR ────────────────────────────────────────────────────
function Sidebar({ theme, view, setView }) {
  const nav = [
    { id: "bridge", label: "Bridge", icon: "◉", primary: true },
    { id: "watchlist", label: "Watchlist", icon: "★" },
    { id: "kbq", label: "KBQ Workspace", icon: "▦" },
    { id: "wargame", label: "War Game", icon: "⚔" },
    { id: "knowledge", label: "Knowledge", icon: "▤" },
    { id: "replay", label: "Replay", icon: "↻" },
  ];
  const secondary = [
    { id: "reviewer", label: "Reviewer", icon: "◐" },
    { id: "agents", label: "Agents", icon: "○" },
  ];

  return (
    <div style={{ width: 220, borderRight: "1px solid " + theme.border, background: theme.surface, display: "flex", flexDirection: "column", flexShrink: 0 }}>
      {/* Brand */}
      <div style={{ padding: "20px 18px", borderBottom: "1px solid " + theme.border }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 26, height: 26, position: "relative" }}>
            <svg viewBox="0 0 28 28" style={{ width: "100%", height: "100%" }}>
              <circle cx="14" cy="14" r="11" fill="none" stroke={theme.accent} strokeWidth="1.5" />
              <circle cx="14" cy="14" r="6" fill="none" stroke={theme.accent2} strokeWidth="1.5" />
              <circle cx="14" cy="14" r="2" fill={theme.accent} />
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 20, lineHeight: 1, letterSpacing: "-0.01em" }}>
              MarketZero
            </div>
            <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.18em", marginTop: 3 }}>· HELIX</div>
          </div>
        </div>
      </div>

      {/* Primary nav */}
      <div style={{ flex: 1, padding: "16px 10px", overflowY: "auto" }}>
        {nav.map(n => (
          <button key={n.id} onClick={() => setView(n.id)} className="nav-item" style={{
            display: "flex", alignItems: "center", gap: 12, width: "100%",
            background: view === n.id ? theme.surfaceAlt : "transparent",
            border: "none", borderRadius: 8, padding: "10px 12px", marginBottom: 2,
            color: view === n.id ? theme.text : theme.textDim, cursor: "pointer",
            fontFamily: "inherit", fontSize: 13, fontWeight: view === n.id ? 600 : 400,
            textAlign: "left", position: "relative", transition: "all 0.15s",
          }}>
            {view === n.id && <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 2, background: theme.accent, borderRadius: 2 }} />}
            <span style={{ fontSize: 14, color: view === n.id ? theme.accent : theme.textDim, width: 16 }}>{n.icon}</span>
            <span>{n.label}</span>
          </button>
        ))}

        <div style={{ marginTop: 20, marginBottom: 8, padding: "0 12px", fontSize: 9, color: theme.textFaint, letterSpacing: "0.15em" }}>OVERSIGHT</div>
        {secondary.map(n => (
          <button key={n.id} onClick={() => setView(n.id)} className="nav-item" style={{
            display: "flex", alignItems: "center", gap: 12, width: "100%",
            background: view === n.id ? theme.surfaceAlt : "transparent",
            border: "none", borderRadius: 8, padding: "10px 12px", marginBottom: 2,
            color: view === n.id ? theme.text : theme.textDim, cursor: "pointer",
            fontFamily: "inherit", fontSize: 13, fontWeight: view === n.id ? 600 : 400,
            textAlign: "left", position: "relative",
          }}>
            {view === n.id && <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 2, background: theme.accent, borderRadius: 2 }} />}
            <span style={{ fontSize: 14, color: view === n.id ? theme.accent : theme.textDim, width: 16 }}>{n.icon}</span>
            <span>{n.label}</span>
          </button>
        ))}
      </div>

      {/* Agent badges */}
      <div style={{ padding: "12px 14px", borderTop: "1px solid " + theme.border }}>
        <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 10 }}>AGENTS ACTIVE</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {[
            { code: "SE", role: "Sentinel", verb: "SENSE", color: theme.accent },
            { code: "ST", role: "Strategist", verb: "FRAME · SIMULATE", color: theme.accent2 },
            { code: "CO", role: "Coach", verb: "LEARN · REVIEW", color: theme.ok },
          ].map(a => (
            <div key={a.code} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 24, height: 24, borderRadius: 6, background: a.color + "25", color: a.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>
                {a.code}
              </div>
              <div>
                <div style={{ fontSize: 11, color: theme.text }}>{a.role}</div>
                <div style={{ fontSize: 8, color: theme.textFaint, letterSpacing: "0.12em" }}>{a.verb}</div>
              </div>
            </div>
          ))}
        </div>
        <button onClick={() => setView("connectors")} style={{
          marginTop: 12, width: "100%", background: "transparent", border: "1px solid " + theme.border,
          borderRadius: 6, padding: "6px 10px", color: theme.textDim, cursor: "pointer",
          fontFamily: "inherit", fontSize: 10, letterSpacing: "0.1em", display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span>Connectors</span>
          <span style={{ color: theme.textFaint }}>→</span>
        </button>
      </div>
    </div>
  );
}

// ─── HEADER ─────────────────────────────────────────────────────
function Header({ theme, themeMode, setThemeMode, decisionsOpen, setDecisionsOpen, now }) {
  return (
    <div style={{ borderBottom: "1px solid " + theme.border, padding: "12px 24px", display: "flex", alignItems: "center", gap: 20, background: theme.surface, position: "sticky", top: 0, zIndex: 100 }}>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: theme.textDim }}>
          <div style={{ position: "relative", width: 8, height: 8, borderRadius: "50%", background: theme.ok }} className="pulse-dot" />
          <span>11 agents · live</span>
        </div>

        <button onClick={() => setDecisionsOpen(!decisionsOpen)} style={{
          background: theme.surfaceAlt, border: "1px solid " + theme.border, borderRadius: 8,
          padding: "6px 12px", color: theme.text, cursor: "pointer", fontFamily: "inherit", fontSize: 11,
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <span style={{ color: theme.accent }}>◆</span>
          <span>Decisions</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", color: theme.textDim }}>· 47</span>
        </button>

        <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: theme.textDim }}>
          {new Date(now).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>

        <div style={{ display: "flex", gap: 2, padding: 3, background: theme.surfaceAlt, borderRadius: 8 }}>
          {["dark", "hybrid", "light"].map(t => (
            <button key={t} onClick={() => setThemeMode(t)} style={{
              padding: "4px 10px", borderRadius: 6, border: "none",
              background: themeMode === t ? theme.accent : "transparent",
              color: themeMode === t ? theme.bg : theme.textDim,
              fontSize: 9, fontFamily: "inherit", fontWeight: 600,
              cursor: "pointer", letterSpacing: "0.05em", textTransform: "uppercase",
            }}>{t}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── BRIDGE ─────────────────────────────────────────────────────
function Bridge({ theme, signals, moments, openMoment, openFrame, twinPulse, bridgeMode, setBridgeMode }) {
  const topMoment = moments[0];
  const [categoryFilter, setCategoryFilter] = useState("all");
  const filteredSignals = categoryFilter === "all" ? signals : signals.filter(s => s.category === categoryFilter);
  const sorted = [...filteredSignals].sort((a, b) => b.materiality - a.materiality);

  return (
    <div style={{ padding: 20 }}>
      {/* Mode toggle + hero */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 4, padding: 4, background: theme.surface, border: "1px solid " + theme.border, borderRadius: 10 }}>
          {[
            { id: "live", label: "Live" },
            { id: "digest_today", label: "Today's Digest" },
            { id: "digest_week", label: "This Week" },
          ].map(m => (
            <button key={m.id} onClick={() => setBridgeMode(m.id)} style={{
              padding: "6px 14px", borderRadius: 6, border: "none",
              background: bridgeMode === m.id ? theme.surfaceAlt : "transparent",
              color: bridgeMode === m.id ? theme.text : theme.textDim,
              cursor: "pointer", fontFamily: "inherit", fontSize: 11, fontWeight: 500,
            }}>{m.label}</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", fontSize: 11, color: theme.textDim }}>
          {bridgeMode === "live" ? "Continuous monitoring" : bridgeMode === "digest_today" ? "Top signals & moments for today" : "Week-in-review"}
        </div>
      </div>

      {/* Hero moment strip */}
      <div className="fade-in" style={{ marginBottom: 20, padding: "18px 24px", background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: theme.warn, position: "relative" }} className="pulse-dot" />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 4 }}>MOST URGENT · NEXT 72H</div>
          <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 22, lineHeight: 1.25, letterSpacing: "-0.01em" }}>
            {topMoment.title}
          </div>
        </div>
        <button onClick={() => openMoment(topMoment)} style={{
          background: theme.accent, border: "none", borderRadius: 8,
          padding: "10px 16px", color: "#fff", cursor: "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 600,
        }}>Open Moment →</button>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>EV AT STAKE</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 600, color: theme.accent }}>
            ${topMoment.ev_at_stake_musd}M
          </div>
        </div>
      </div>

      {/* Three zones */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 1fr) minmax(400px, 1.4fr) minmax(360px, 1fr)", gap: 16 }}>
        {/* PULSE */}
        <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 18, display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 240px)", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div>
              <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 17 }}>Pulse</div>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em", marginTop: 2 }}>SENSING FEED · {sorted.length} SIGNALS</div>
            </div>
            <div style={{ fontSize: 10, color: theme.textDim, display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: theme.ok }} className="pulse-soft" />
              live
            </div>
          </div>

          {/* Category filters */}
          <div style={{ display: "flex", gap: 4, marginBottom: 12, overflowX: "auto", paddingBottom: 4 }}>
            <CatChip theme={theme} cat={{ id: "all", label: "All", color: theme.textDim }} active={categoryFilter === "all"} onClick={() => setCategoryFilter("all")} />
            {IMPACT_CATEGORIES.map(c => (
              <CatChip key={c.id} theme={theme} cat={c} active={categoryFilter === c.id} onClick={() => setCategoryFilter(c.id)} />
            ))}
          </div>

          {/* Signals */}
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
            {sorted.map(s => <SignalCard key={s.id} theme={theme} signal={s} onFrame={() => openFrame(s)} />)}
          </div>

          <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid " + theme.border, fontSize: 10, color: theme.textFaint, textAlign: "center" }}>
            Browse all signals →
          </div>
        </div>

        {/* TWIN */}
        <Twin theme={theme} twinPulse={twinPulse} />

        {/* MOMENTS */}
        <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 17 }}>AI Moments</div>
            <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em", marginTop: 2 }}>RANKED BY EV × TIME-DECAY</div>
          </div>
          {moments.map((m, i) => <MomentCard key={m.id} theme={theme} moment={m} idx={i} onClick={() => openMoment(m)} />)}
        </div>
      </div>
    </div>
  );
}

function CatChip({ theme, cat, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      flexShrink: 0, padding: "4px 10px", borderRadius: 12, border: "none",
      background: active ? cat.color + "25" : theme.surfaceAlt,
      color: active ? cat.color : theme.textDim,
      cursor: "pointer", fontFamily: "inherit", fontSize: 10, fontWeight: 500,
    }}>{cat.label}</button>
  );
}

function SignalCard({ theme, signal, onFrame }) {
  const cat = IMPACT_CATEGORIES.find(c => c.id === signal.category) || { color: theme.textDim, label: signal.category };
  const tierColor = signal.tier === 1 ? theme.danger : signal.tier === 2 ? theme.warn : theme.textFaint;
  const stream = SOURCE_STREAMS[signal.stream] || signal.stream;
  const [hover, setHover] = useState(false);
  const showFrame = signal.tier === 1 || (signal.tier === 2 && hover);

  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        padding: "10px 12px", borderRadius: 8,
        background: hover ? theme.surfaceAlt : "transparent",
        borderLeft: "2px solid " + cat.color,
        opacity: signal.tier === 3 ? 0.7 : 1, transition: "all 0.15s",
        display: "flex", flexDirection: "column", gap: 6,
      }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        {/* Materiality dial */}
        <div style={{ position: "relative", width: 36, height: 36, flexShrink: 0 }}>
          <svg viewBox="0 0 36 36" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
            <circle cx="18" cy="18" r="14" fill="none" stroke={theme.border} strokeWidth="2" />
            <circle cx="18" cy="18" r="14" fill="none"
              stroke={tierColor} strokeWidth="2.5"
              strokeDasharray={`${(signal.materiality / 10) * 88} 88`} strokeLinecap="round" />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: tierColor, fontFamily: "'JetBrains Mono', monospace" }}>
            {signal.materiality.toFixed(1)}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
            <span style={{ padding: "1px 6px", background: cat.color + "25", color: cat.color, borderRadius: 4, fontSize: 9, fontWeight: 600 }}>{cat.label}</span>
            <span style={{ padding: "1px 6px", background: tierColor + "25", color: tierColor, borderRadius: 4, fontSize: 9, fontWeight: 700, letterSpacing: "0.08em" }}>TIER {signal.tier}</span>
            <span style={{ fontSize: 9, color: theme.textFaint, fontFamily: "'JetBrains Mono', monospace" }}>{stream}</span>
            {signal.company !== "—" && <span style={{ fontSize: 9, color: theme.textFaint }}>· {signal.company.toUpperCase()}</span>}
          </div>
          <div style={{ fontSize: 12, color: theme.text, lineHeight: 1.4, fontWeight: 500 }}>{signal.title}</div>
          <div style={{ fontSize: 10, color: theme.textFaint, marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>{signal.source}</div>
        </div>
      </div>

      {showFrame && (
        <button onClick={onFrame} style={{
          alignSelf: "flex-end", background: theme.accent2, border: "none", borderRadius: 6,
          padding: "4px 10px", color: "#fff", cursor: "pointer",
          fontFamily: "inherit", fontSize: 10, fontWeight: 600, letterSpacing: "0.05em",
        }}>FRAME AS DECISION →</button>
      )}
    </div>
  );
}

function MomentCard({ theme, moment, idx, onClick }) {
  const cat = IMPACT_CATEGORIES.find(c => c.id === moment.category) || { color: theme.accent, label: moment.category };
  const hours = moment.expires_hours;
  const urgencyColor = hours < 72 ? theme.danger : hours < 200 ? theme.warn : theme.textDim;

  return (
    <div onClick={onClick} className="fade-up" style={{
      background: theme.surfaceAlt, border: "1px solid " + theme.border,
      borderRadius: 10, padding: 14, cursor: "pointer", animationDelay: (idx * 0.06) + "s",
      transition: "all 0.2s",
    }} onMouseEnter={e => { e.currentTarget.style.borderColor = theme.accent; e.currentTarget.style.transform = "translateY(-2px)"; }}
       onMouseLeave={e => { e.currentTarget.style.borderColor = theme.border; e.currentTarget.style.transform = "translateY(0)"; }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: theme.textFaint }}>MOMENT.{String(idx + 1).padStart(2, "0")}</span>
        <span style={{ padding: "1px 6px", background: cat.color + "25", color: cat.color, borderRadius: 4, fontSize: 9, fontWeight: 600 }}>{cat.label}</span>
        <span style={{ marginLeft: "auto", fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: urgencyColor, fontWeight: 600 }}>
          {hours < 24 ? hours + "h" : Math.floor(hours / 24) + "d"}
        </span>
      </div>
      <div style={{ fontSize: 12, color: theme.text, fontWeight: 500, lineHeight: 1.4, marginBottom: 10 }}>{moment.title}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 8, color: theme.textFaint, letterSpacing: "0.08em" }}>EV @ STAKE</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, color: theme.accent, fontWeight: 600 }}>${moment.ev_at_stake_musd}M</div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 8, color: theme.textFaint, letterSpacing: "0.08em", marginBottom: 3 }}>BELIEF Δ</div>
          <BeliefBar theme={theme} from={moment.delta_belief.from} to={moment.delta_belief.to} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 3 }}>
        {moment.plays.map(p => (
          <div key={p.id} style={{
            flex: 1, height: 3, borderRadius: 1.5,
            background: p.kind === "aggressive" ? theme.danger : p.kind === "balanced" ? theme.accent : theme.ok,
            opacity: 0.7,
          }} />
        ))}
      </div>
    </div>
  );
}

function BeliefBar({ theme, from, to }) {
  return (
    <div style={{ height: 4, background: theme.border, borderRadius: 2, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", left: from * 100 + "%", top: 0, bottom: 0, width: (to - from) * 100 + "%", background: theme.accent }} />
      <div style={{ position: "absolute", left: to * 100 + "%", top: -2, bottom: -2, width: 2, background: theme.accent }} />
    </div>
  );
}

// ─── TWIN ───────────────────────────────────────────────────────
function Twin({ theme, twinPulse }) {
  const [hoverNode, setHoverNode] = useState(null);
  const W = 600, H = 440, cx = W / 2, cy = H / 2;

  const nodes = useMemo(() => ([
    { id: "wegovy", group: "novo", label: "Wegovy", x: 160, y: 160, r: 26, color: "#003b71", core: true, share: 38 },
    { id: "ozempic", group: "novo", label: "Ozempic", x: 130, y: 250, r: 22, color: "#003b71", share: 24 },
    { id: "cagrisema", group: "novo", label: "CagriSema", x: 190, y: 330, r: 16, color: "#003b71", phase: "P3" },
    { id: "tirzepatide", group: "lilly", label: "Tirzepatide", x: 420, y: 180, r: 28, color: "#d52b1e", share: 32 },
    { id: "orforglipron", group: "lilly", label: "Orforglipron", x: 470, y: 270, r: 20, color: "#d52b1e", phase: "P3 oral", pulsing: true },
    { id: "retatrutide", group: "lilly", label: "Retatrutide", x: 430, y: 340, r: 18, color: "#d52b1e", phase: "P3" },
    { id: "maritide", group: "amgen", label: "MariTide", x: 470, y: 110, r: 16, color: "#0063c3", phase: "P3 monthly" },
    { id: "danuglipron", group: "pfizer", label: "Danuglipron", x: 320, y: 90, r: 14, color: "#0093d0", phase: "P2 oral" },
    { id: "patients", group: "market", label: "Patients", x: 290, y: 220, r: 30, color: theme.accent, core: true },
    { id: "payers", group: "market", label: "Payers", x: 90, y: 90, r: 18, color: theme.accent2 },
    { id: "cms", group: "regulator", label: "CMS NCD", x: 530, y: 50, r: 14, color: theme.warn, pulsing: true },
    { id: "fda", group: "regulator", label: "FDA", x: 60, y: 380, r: 14, color: theme.warn },
  ]), [theme]);

  const edges = [
    { from: "wegovy", to: "patients", weight: 0.7 },
    { from: "ozempic", to: "patients", weight: 0.5 },
    { from: "tirzepatide", to: "patients", weight: 0.6 },
    { from: "patients", to: "payers", weight: 0.8 },
    { from: "patients", to: "cms", weight: 0.9, ghost: true },
    { from: "orforglipron", to: "patients", weight: 0.4, future: true },
    { from: "retatrutide", to: "patients", weight: 0.3, future: true },
    { from: "cagrisema", to: "patients", weight: 0.3, future: true },
    { from: "maritide", to: "patients", weight: 0.2, future: true },
    { from: "danuglipron", to: "patients", weight: 0.15, future: true },
    { from: "fda", to: "wegovy", weight: 0.3 },
  ];

  const getNode = id => nodes.find(n => n.id === id);

  return (
    <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 18, display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 240px)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 17 }}>Digital Twin · GLP-1 Market</div>
          <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em", marginTop: 2 }}>POSTERIOR STATE · UPDATED {twinPulse}s AGO</div>
        </div>
        <div style={{ display: "flex", gap: 14 }}>
          {[{ l: "You", v: "62%", c: "#003b71" }, { l: "Rivals", v: "32%", c: "#d52b1e" }, { l: "Conf", v: "0.79", c: theme.accent }].map(s => (
            <div key={s.l} style={{ textAlign: "right" }}>
              <div style={{ fontSize: 8, color: theme.textFaint, letterSpacing: "0.1em" }}>{s.l.toUpperCase()}</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600, color: s.c }}>{s.v}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, position: "relative", background: theme.bg, borderRadius: 8, border: "1px solid " + theme.border, overflow: "hidden", minHeight: 360 }}>
        <svg viewBox={"0 0 " + W + " " + H} style={{ width: "100%", height: "100%" }}>
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke={theme.border} strokeWidth="0.5" opacity="0.3" />
            </pattern>
            <radialGradient id="patientglow">
              <stop offset="0%" stopColor={theme.accent} stopOpacity="0.3" />
              <stop offset="100%" stopColor={theme.accent} stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect width={W} height={H} fill="url(#grid)" />
          <circle cx={290} cy={220} r={75} fill="url(#patientglow)" />

          {edges.map((e, i) => {
            const a = getNode(e.from), b = getNode(e.to);
            if (!a || !b) return null;
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={e.future ? theme.accent2 : e.ghost ? theme.warn : theme.textDim}
              strokeWidth={e.weight * 2.5}
              opacity={e.future ? 0.35 : 0.5}
              strokeDasharray={e.future || e.ghost ? "4 4" : "none"} />;
          })}

          {nodes.map(n => (
            <g key={n.id} style={{ cursor: "pointer" }}
              onMouseEnter={() => setHoverNode(n.id)} onMouseLeave={() => setHoverNode(null)}>
              {n.pulsing && (
                <circle cx={n.x} cy={n.y} r={n.r + 4} fill={n.color} opacity="0.15">
                  <animate attributeName="r" values={(n.r + 2) + ";" + (n.r + 12) + ";" + (n.r + 2)} dur="2.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.3;0;0.3" dur="2.5s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={n.x} cy={n.y} r={n.r} fill={n.color} opacity={n.core ? 1 : 0.85}
                stroke={hoverNode === n.id ? theme.text : "transparent"} strokeWidth={2} />
              <text x={n.x} y={n.y + n.r + 13} textAnchor="middle" fill={theme.text} fontSize="9.5" fontWeight={n.core ? 600 : 500} fontFamily="Inter">
                {n.label}
              </text>
              {n.share > 0 && (
                <text x={n.x} y={n.y + 3} textAnchor="middle" fill="#fff" fontSize="10" fontWeight={700} fontFamily="JetBrains Mono">{n.share}%</text>
              )}
              {n.phase && (
                <text x={n.x} y={n.y + n.r + 25} textAnchor="middle" fill={theme.textFaint} fontSize="8" fontFamily="JetBrains Mono">{n.phase}</text>
              )}
            </g>
          ))}
        </svg>

        {hoverNode && (
          <div style={{ position: "absolute", bottom: 10, left: 10, padding: "8px 12px", background: theme.surface, border: "1px solid " + theme.border, borderRadius: 8, fontSize: 11, color: theme.text, maxWidth: 260 }}>
            <div style={{ fontWeight: 600, marginBottom: 3 }}>{getNode(hoverNode).label}</div>
            <div style={{ color: theme.textDim, lineHeight: 1.5, fontSize: 10 }}>
              {hoverNode === "patients" && "~12.3M eligible US patients · 38% on therapy"}
              {hoverNode === "orforglipron" && "Lilly oral. Twin posterior P(Q1 '27 launch) = 0.41"}
              {hoverNode === "cms" && "Draft NCD active · 19 days to comment close"}
              {!["patients", "orforglipron", "cms"].includes(hoverNode) && "Click to FRAME AS DECISION"}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── MOMENT VIEW ────────────────────────────────────────────────
function MomentView({ theme, themeMode, moment, signals, close }) {
  const useLight = themeMode === "hybrid";
  const m = useLight ? {
    bg: "#fafafa", surface: "#ffffff", surfaceAlt: "#f3f4f6", border: "#e5e7eb",
    text: "#111827", textDim: "#6b7280", textFaint: "#9ca3af",
    accent: "#0d9488", accent2: "#7c3aed", danger: "#dc2626", warn: "#d97706", ok: "#059669",
  } : theme;

  const [selectedPlay, setSelectedPlay] = useState(moment.plays[1]);
  const chainSignals = signals.filter(s => moment.signal_chain.includes(s.id));

  return (
    <div className="fade-in" style={{
      position: "fixed", inset: 0, background: m.bg, color: m.text, zIndex: 200,
      overflow: "auto", padding: "32px 48px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <button onClick={close} style={{
          background: m.surface, border: "1px solid " + m.border, borderRadius: 8,
          padding: "8px 14px", color: m.textDim, cursor: "pointer", fontFamily: "inherit", fontSize: 12,
        }}>← Back</button>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: m.textFaint, letterSpacing: "0.08em" }}>
          MOMENT.{moment.id.toUpperCase()} · {moment.expires_hours}H REMAINING
        </div>
      </div>

      <div style={{ marginBottom: 28, maxWidth: 900 }}>
        <div style={{ fontSize: 10, color: m.textFaint, letterSpacing: "0.15em", marginBottom: 10 }}>STRATEGIC MOMENT</div>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 38, lineHeight: 1.15, letterSpacing: "-0.02em", marginBottom: 14 }}>
          {moment.title}
        </div>
        <div style={{ fontSize: 15, lineHeight: 1.6, color: m.textDim, maxWidth: 720 }}>
          {moment.summary}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 24 }}>
        <div>
          <div style={{ marginBottom: 12, display: "flex", alignItems: "baseline", gap: 12 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 20 }}>Plays</div>
            <div style={{ fontSize: 10, color: m.textFaint, letterSpacing: "0.1em" }}>STRATEGIST AGENTS · 3 PERSONAS</div>
          </div>

          <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
            {moment.plays.map(p => <PlayCard key={p.id} theme={m} play={p} selected={selectedPlay.id === p.id} onSelect={() => setSelectedPlay(p)} />)}
          </div>

          <div style={{ background: m.surface, border: "1px solid " + m.border, borderRadius: 10, padding: 18, marginBottom: 20 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 16, marginBottom: 3 }}>Outcome Distribution</div>
            <div style={{ fontSize: 10, color: m.textFaint, letterSpacing: "0.08em", marginBottom: 14 }}>
              MONTE CARLO · 10,000 RUNS · {selectedPlay.label.toUpperCase()}
            </div>
            <OutcomeDist theme={m} play={selectedPlay} />
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button style={{ flex: 1, background: m.accent, border: "none", borderRadius: 8, padding: "14px 20px", color: "#fff", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 600 }}>
              ⚔ Open as War Room
            </button>
            <button style={{ background: m.surface, border: "1px solid " + m.border, borderRadius: 8, padding: "14px 20px", color: m.text, cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 600 }}>
              Defer
            </button>
            <button style={{ background: m.text, border: "none", borderRadius: 8, padding: "14px 20px", color: m.bg, cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 600 }}>
              Commit Decision →
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ background: m.surface, border: "1px solid " + m.border, borderRadius: 10, padding: 18 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 16, marginBottom: 3 }}>Signal Chain</div>
            <div style={{ fontSize: 10, color: m.textFaint, letterSpacing: "0.08em", marginBottom: 14 }}>WHY THIS MOMENT EXISTS</div>
            {chainSignals.map((sig, i) => {
              const cat = IMPACT_CATEGORIES.find(c => c.id === sig.category);
              return (
                <div key={sig.id} style={{ position: "relative", paddingLeft: 22, paddingBottom: i === chainSignals.length - 1 ? 0 : 14, borderLeft: i === chainSignals.length - 1 ? "none" : "1px dashed " + m.border }}>
                  <div style={{ position: "absolute", left: -5, top: 4, width: 10, height: 10, borderRadius: "50%", background: cat.color, border: "2px solid " + m.surface }} />
                  <div style={{ fontSize: 9, color: cat.color, letterSpacing: "0.08em", fontWeight: 600, marginBottom: 3 }}>
                    {cat.label.toUpperCase()} · {sig.source}
                  </div>
                  <div style={{ fontSize: 11.5, color: m.text, fontWeight: 500, lineHeight: 1.4, marginBottom: 3 }}>{sig.title}</div>
                </div>
              );
            })}
          </div>

          <div style={{ background: m.surface, border: "1px solid " + m.border, borderRadius: 10, padding: 18 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 16, marginBottom: 14 }}>Belief Shift</div>
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 9, color: m.textFaint }}>PRIOR</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: m.textDim }}>{Math.round(moment.delta_belief.from * 100)}%</div>
              </div>
              <div style={{ fontSize: 20, color: m.accent }}>→</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 9, color: m.textFaint }}>POSTERIOR</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: m.accent }}>{Math.round(moment.delta_belief.to * 100)}%</div>
              </div>
            </div>
            <BeliefBar theme={m} from={moment.delta_belief.from} to={moment.delta_belief.to} />
            <div style={{ fontSize: 10, color: m.textDim, marginTop: 8 }}>{moment.delta_belief.label}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlayCard({ theme, play, selected, onSelect }) {
  const kindColor = play.kind === "aggressive" ? theme.danger : play.kind === "balanced" ? theme.accent : theme.ok;
  return (
    <div onClick={onSelect} style={{
      background: theme.surface, border: "2px solid " + (selected ? theme.accent : theme.border),
      borderRadius: 10, padding: 16, cursor: "pointer", transition: "all 0.2s",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <div style={{ fontSize: 9, padding: "2px 8px", borderRadius: 10, background: kindColor + "20", color: kindColor, fontWeight: 700, letterSpacing: "0.08em" }}>
          {play.kind.toUpperCase()}
        </div>
        {selected && <div style={{ fontSize: 9, padding: "2px 8px", borderRadius: 10, background: theme.accent, color: "#fff", fontWeight: 700, letterSpacing: "0.08em" }}>SELECTED</div>}
      </div>
      <div style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.4, marginBottom: 12 }}>{play.label}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        {[
          { l: "EV", v: "$" + play.ev + "M", c: theme.accent },
          { l: "Var", v: "$" + play.ev_var + "M", c: theme.textDim },
          { l: "P(win)", v: Math.round(play.prob_success * 100) + "%", c: theme.ok },
        ].map(s => (
          <div key={s.l}>
            <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.08em" }}>{s.l.toUpperCase()}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600, color: s.c }}>{s.v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function OutcomeDist({ theme, play }) {
  const bars = Array.from({ length: 22 }, (_, i) => {
    const x = -2.5 + (i / 21) * 5;
    return { x, h: Math.exp(-(x * x) / 1.5) };
  });
  const peak = Math.max(...bars.map(b => b.h));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 70, marginBottom: 10 }}>
        {bars.map((b, i) => (
          <div key={i} style={{ flex: 1, height: (b.h / peak) * 100 + "%",
            background: Math.abs(b.x) < 1 ? theme.accent : theme.accent + "60", borderRadius: "2px 2px 0 0" }} />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: theme.textFaint }}>
        <span>${play.ev - play.ev_var * 2}M (P05)</span>
        <span style={{ color: theme.text, fontWeight: 600 }}>${play.ev}M expected</span>
        <span>${play.ev + play.ev_var * 2}M (P95)</span>
      </div>
    </div>
  );
}

// ─── DECISION FRAME MODAL ───────────────────────────────────────
function DecisionFrameModal({ theme, signal, close }) {
  const [question, setQuestion] = useState("");
  const [decisionClass, setDecisionClass] = useState("other");
  const [horizon, setHorizon] = useState("30");
  const [nextSteps, setNextSteps] = useState({ moment: true, warroom: false, kbq: false });

  return (
    <div onClick={close} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 300,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={e => e.stopPropagation()} className="fade-up" style={{
        background: theme.surface, border: "1px solid " + theme.border, borderRadius: 14,
        padding: 28, maxWidth: 560, width: "100%", color: theme.text,
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 10, color: theme.accent2, letterSpacing: "0.15em", fontWeight: 600, marginBottom: 4 }}>FRAME AS DECISION</div>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 24 }}>New Decision Frame</div>
          </div>
          <button onClick={close} style={{ background: "transparent", border: "1px solid " + theme.border, borderRadius: 6, width: 30, height: 30, color: theme.textDim, cursor: "pointer" }}>✕</button>
        </div>

        {/* Source signal */}
        <div style={{ padding: 12, background: theme.surfaceAlt, borderRadius: 8, marginBottom: 18 }}>
          <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em", marginBottom: 6 }}>TRIGGERING SIGNAL</div>
          <div style={{ fontSize: 12, color: theme.text, fontWeight: 500, marginBottom: 4 }}>{signal.title}</div>
          <div style={{ display: "flex", gap: 6, fontSize: 9, color: theme.textDim }}>
            <span style={{ padding: "1px 6px", background: theme.danger + "25", color: theme.danger, borderRadius: 4, fontWeight: 700 }}>TIER {signal.tier}</span>
            <span>{IMPACT_CATEGORIES.find(c => c.id === signal.category)?.label}</span>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.1em", display: "block", marginBottom: 6 }}>QUESTION TO RESOLVE</label>
          <textarea value={question} onChange={e => setQuestion(e.target.value)}
            placeholder="What is the decision this signal forces us to make?"
            style={{
              width: "100%", minHeight: 70, background: theme.bg, border: "1px solid " + theme.border,
              borderRadius: 6, padding: 10, color: theme.text, fontFamily: "inherit", fontSize: 13, resize: "vertical",
            }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 16 }}>
          <div>
            <label style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.1em", display: "block", marginBottom: 6 }}>DECISION CLASS</label>
            <select value={decisionClass} onChange={e => setDecisionClass(e.target.value)} style={{
              width: "100%", background: theme.bg, border: "1px solid " + theme.border, borderRadius: 6,
              padding: "8px 10px", color: theme.text, fontFamily: "inherit", fontSize: 12,
            }}>
              <option value="pricing">Pricing</option>
              <option value="indication">Indication launch</option>
              <option value="trial">Trial design</option>
              <option value="ma">M&A / partnership</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.1em", display: "block", marginBottom: 6 }}>TIME HORIZON</label>
            <select value={horizon} onChange={e => setHorizon(e.target.value)} style={{
              width: "100%", background: theme.bg, border: "1px solid " + theme.border, borderRadius: 6,
              padding: "8px 10px", color: theme.text, fontFamily: "inherit", fontSize: 12,
            }}>
              <option value="7">{"< 7 days"}</option>
              <option value="30">{"< 30 days"}</option>
              <option value="90">{"< 90 days"}</option>
              <option value="365">{"< 1 year"}</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.1em", display: "block", marginBottom: 8 }}>SUGGESTED NEXT STEPS</label>
          {[
            { id: "moment", label: "Open as Moment (auto-generate plays)" },
            { id: "warroom", label: "Open War Room (manual move builder)" },
            { id: "kbq", label: "Trigger KBQ-3 refresh on affected products" },
          ].map(s => (
            <label key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", cursor: "pointer" }}>
              <input type="checkbox" checked={nextSteps[s.id]} onChange={e => setNextSteps(prev => ({ ...prev, [s.id]: e.target.checked }))} />
              <span style={{ fontSize: 12, color: theme.text }}>{s.label}</span>
            </label>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={close} style={{
            background: "transparent", border: "1px solid " + theme.border, borderRadius: 8,
            padding: "10px 18px", color: theme.textDim, cursor: "pointer", fontFamily: "inherit", fontSize: 12,
          }}>Cancel</button>
          <button onClick={close} disabled={!question} style={{
            background: question ? theme.accent : theme.surfaceAlt, border: "none", borderRadius: 8,
            padding: "10px 18px", color: question ? "#fff" : theme.textFaint,
            cursor: question ? "pointer" : "not-allowed", fontFamily: "inherit", fontSize: 12, fontWeight: 600,
          }}>Create Frame →</button>
        </div>
      </div>
    </div>
  );
}

// ─── DECISION LEDGER PANEL ──────────────────────────────────────
function DecisionLedgerPanel({ theme, close }) {
  return (
    <div onClick={close} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 250,
      display: "flex", justifyContent: "flex-end",
    }}>
      <div onClick={e => e.stopPropagation()} className="slide-right" style={{
        width: 480, background: theme.surface, borderLeft: "1px solid " + theme.border,
        height: "100vh", overflow: "auto", padding: 28, color: theme.text,
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 4 }}>DECISION LEDGER</div>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 24 }}>Recent Decisions</div>
          </div>
          <button onClick={close} style={{ background: "transparent", border: "1px solid " + theme.border, borderRadius: 6, width: 30, height: 30, color: theme.textDim, cursor: "pointer" }}>✕</button>
        </div>

        <div style={{ marginBottom: 20, padding: 14, background: theme.surfaceAlt, borderRadius: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>TOTAL COMMITS</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: theme.accent }}>47</div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>PENDING FRAMES</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: theme.warn }}>2</div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>OUTCOMES TRACKED</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, color: theme.ok }}>23</div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {SEED_DECISIONS.map(d => {
            const cat = IMPACT_CATEGORIES.find(c => c.id === d.class) || { color: theme.textDim, label: d.class };
            return (
              <div key={d.id} style={{ padding: 14, background: theme.surfaceAlt, border: "1px solid " + theme.border, borderRadius: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ padding: "2px 8px", background: cat.color + "25", color: cat.color, borderRadius: 4, fontSize: 9, fontWeight: 600 }}>{cat.label}</span>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: theme.textFaint }}>{d.date}</span>
                  </div>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: theme.accent, fontWeight: 600 }}>${d.ev_at_stake}M</span>
                </div>
                <div style={{ fontSize: 13, color: theme.text, fontWeight: 500, marginBottom: 6 }}>{d.title}</div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: theme.textDim }}>
                  <span>by {d.committedBy}</span>
                  <span style={{ color: d.outcome === "Pending" ? theme.warn : d.outcome.includes("Confirmed") ? theme.ok : theme.textDim }}>
                    {d.outcome}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <button style={{
          width: "100%", marginTop: 16, background: theme.surface, border: "1px solid " + theme.border, borderRadius: 8,
          padding: "10px", color: theme.textDim, cursor: "pointer", fontFamily: "inherit", fontSize: 12,
        }}>Open full ledger →</button>
      </div>
    </div>
  );
}

// ─── WATCHLIST VIEW ─────────────────────────────────────────────
function WatchlistView({ theme }) {
  return (
    <div className="fade-in" style={{ padding: 32 }}>
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <div style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 8 }}>SAVED INTELLIGENCE</div>
          <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 36, letterSpacing: "-0.02em" }}>Watchlists</div>
          <div style={{ fontSize: 13, color: theme.textDim, marginTop: 6, maxWidth: 600, lineHeight: 1.6 }}>
            Saved filter expressions that drive personalized monitoring, materiality calibration, and digest content.
          </div>
        </div>
        <button style={{
          background: theme.accent, border: "none", borderRadius: 8,
          padding: "10px 18px", color: "#fff", cursor: "pointer", fontFamily: "inherit", fontSize: 12, fontWeight: 600,
        }}>+ New Watchlist</button>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {SEED_WATCHLISTS.map(w => (
          <div key={w.id} style={{
            background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12,
            padding: 18, display: "grid", gridTemplateColumns: "1fr 100px 100px 80px", gap: 16, alignItems: "center",
            cursor: "pointer", transition: "all 0.2s",
          }} onMouseEnter={e => e.currentTarget.style.borderColor = w.color}
             onMouseLeave={e => e.currentTarget.style.borderColor = theme.border}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: w.color }} />
                <div style={{ fontSize: 14, color: theme.text, fontWeight: 600 }}>{w.name}</div>
              </div>
              <div style={{ fontSize: 11, color: theme.textDim, fontFamily: "'JetBrains Mono', monospace" }}>{w.filter}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>ACTIVE</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600, color: theme.text }}>{w.active}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em" }}>LAST HIT</div>
              <div style={{ fontSize: 11, color: theme.textDim }}>{w.lastHit}</div>
            </div>
            <button style={{
              background: w.color + "20", border: "1px solid " + w.color + "40", borderRadius: 6,
              padding: "6px 12px", color: w.color, cursor: "pointer", fontFamily: "inherit", fontSize: 11, fontWeight: 600,
            }}>Open →</button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 32, padding: 24, background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12 }}>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 18, marginBottom: 16 }}>How Watchlists work</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          {[
            { n: "01", t: "Filter expression", d: "Combine impact categories, companies, tiers, keywords, source streams into a saved query" },
            { n: "02", t: "Personalized materiality", d: "Signals matching your Watchlists get a materiality bonus — they surface higher in your Pulse" },
            { n: "03", t: "Auto-actions", d: "Optionally trigger KBQ refreshes, push to Slack, or include in Daily Digest" },
          ].map(s => (
            <div key={s.n}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: theme.accent, marginBottom: 6, fontWeight: 600 }}>{s.n}</div>
              <div style={{ fontSize: 13, color: theme.text, fontWeight: 600, marginBottom: 4 }}>{s.t}</div>
              <div style={{ fontSize: 11, color: theme.textDim, lineHeight: 1.5 }}>{s.d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── REVIEWER VIEW ──────────────────────────────────────────────
function ReviewerView({ theme }) {
  return (
    <div className="fade-in" style={{ padding: 32 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 8 }}>LEARN · RECALIBRATE</div>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 36, letterSpacing: "-0.02em" }}>Reviewer</div>
        <div style={{ fontSize: 13, color: theme.textDim, marginTop: 6, maxWidth: 640, lineHeight: 1.6 }}>
          Coach agent observations on your decision patterns. Advisory, never authoritative. Every observation cites evidence.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 24 }}>
        {[
          { label: "Decisions this Q", val: "12", color: theme.text },
          { label: "Outperformed system", val: "58%", color: theme.ok },
          { label: "Coach observations", val: "7", color: theme.accent2 },
        ].map(s => (
          <div key={s.label} style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.1em", marginBottom: 4 }}>{s.label.toUpperCase()}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 26, fontWeight: 600, color: s.color }}>{s.val}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {REVIEWER_OBSERVATIONS.map(o => {
          const kindColor = o.kind === "pattern" ? theme.warn : o.kind === "track-record" ? theme.accent : theme.ok;
          return (
            <div key={o.id} style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 10, padding: 18, borderLeft: "3px solid " + kindColor }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ padding: "2px 8px", background: kindColor + "25", color: kindColor, borderRadius: 4, fontSize: 9, fontWeight: 700, letterSpacing: "0.08em" }}>{o.kind.toUpperCase()}</span>
                <span style={{ fontSize: 10, color: theme.textFaint }}>{o.week}</span>
              </div>
              <div style={{ fontSize: 13, color: theme.text, lineHeight: 1.7 }}>{o.text}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button style={{ background: "transparent", border: "1px solid " + theme.border, borderRadius: 6, padding: "5px 12px", color: theme.textDim, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>View decisions</button>
                <button style={{ background: "transparent", border: "1px solid " + theme.border, borderRadius: 6, padding: "5px 12px", color: theme.textDim, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>Mark as noted</button>
                <button style={{ background: "transparent", border: "1px solid " + theme.border, borderRadius: 6, padding: "5px 12px", color: theme.textFaint, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>Dismiss</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── AGENTS VIEW ────────────────────────────────────────────────
function AgentsView({ theme }) {
  return (
    <div className="fade-in" style={{ padding: 32 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 8 }}>ACCOUNTABLE AUTOMATION</div>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 36, letterSpacing: "-0.02em" }}>Agents</div>
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        {AGENT_ROSTER.map(a => (
          <div key={a.id} style={{
            background: theme.surface, border: "1px solid " + theme.border, borderRadius: 10, padding: 16,
            display: "grid", gridTemplateColumns: "200px 1fr 160px 100px 100px 70px", gap: 14, alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 13, color: theme.text, fontWeight: 600 }}>{a.name}</div>
              <div style={{ fontSize: 9, color: theme.textFaint, letterSpacing: "0.08em", marginTop: 3 }}>{a.role.toUpperCase()}</div>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: a.status === "active" ? theme.ok : a.status === "watching" ? theme.accent : a.status === "updating" ? theme.warn : theme.textFaint }} className={a.status === "active" ? "pulse-soft" : ""} />
                <span style={{ fontSize: 9, color: theme.textDim, letterSpacing: "0.08em" }}>{a.status.toUpperCase()}</span>
              </div>
              <div style={{ fontSize: 11, color: theme.text }}>{a.activity}</div>
            </div>
            <div style={{ fontSize: 10, color: theme.textDim }}>{a.scope}</div>
            <div>
              <div style={{ fontSize: 9, color: theme.textFaint }}>ACCURACY</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 15, fontWeight: 600, color: a.accuracy > 0.85 ? theme.ok : a.accuracy > 0.75 ? theme.accent : theme.warn }}>
                {(a.accuracy * 100).toFixed(0)}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: theme.textFaint, marginBottom: 4 }}>AUTONOMY</div>
              <div style={{ display: "flex", gap: 2 }}>
                {[1, 2, 3, 4, 5].map(lvl => (
                  <div key={lvl} style={{ width: 10, height: 4, borderRadius: 1, background: lvl <= a.autonomy ? theme.accent2 : theme.border }} />
                ))}
              </div>
            </div>
            <div style={{ textAlign: "right", fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: theme.text }}>{a.calls_today}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── CONNECTORS VIEW ────────────────────────────────────────────
function ConnectorsView({ theme }) {
  const publicSources = [
    { name: "ClinicalTrials.gov", status: "Live", sync: "4 min ago" },
    { name: "PubMed", status: "Live", sync: "12 min ago" },
    { name: "FDA DailyMed", status: "Live", sync: "1 hour ago" },
    { name: "EMA Medicines", status: "Live", sync: "2 hours ago" },
    { name: "CMS ASP / NADAC", status: "Live", sync: "Daily" },
    { name: "FDA Orange Book", status: "Live", sync: "Daily" },
    { name: "Company SEC filings", status: "Live", sync: "30 min ago" },
    { name: "Press release feeds", status: "Partial", sync: "15 min ago" },
  ];
  const paidSources = [
    { name: "Citeline / Trialtrove", status: "Stub" },
    { name: "Evaluate Pharma", status: "Stub" },
    { name: "AlphaSense", status: "Stub" },
    { name: "MMIT / Fingertip", status: "Stub" },
    { name: "Navelin", status: "Stub" },
    { name: "IQVIA", status: "Stub" },
  ];

  return (
    <div className="fade-in" style={{ padding: 32 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: theme.textFaint, letterSpacing: "0.15em", marginBottom: 8 }}>DATA REGISTRY</div>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 36, letterSpacing: "-0.02em" }}>Connectors</div>
        <div style={{ fontSize: 13, color: theme.textDim, marginTop: 6, maxWidth: 640, lineHeight: 1.6 }}>
          Source connectors with status and last-sync. Public sources are live; paid sources require contracts.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 18 }}>Public</div>
            <div style={{ padding: "2px 8px", background: theme.ok + "25", color: theme.ok, borderRadius: 4, fontSize: 9, fontWeight: 700 }}>{publicSources.length} LIVE</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {publicSources.map(s => (
              <div key={s.name} style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", background: theme.surfaceAlt, borderRadius: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: s.status === "Live" ? theme.ok : theme.warn }} />
                  <span style={{ fontSize: 12, color: theme.text }}>{s.name}</span>
                </div>
                <span style={{ fontSize: 10, color: theme.textFaint, fontFamily: "'JetBrains Mono', monospace" }}>{s.sync}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 18 }}>Paid</div>
            <div style={{ padding: "2px 8px", background: theme.warn + "25", color: theme.warn, borderRadius: 4, fontSize: 9, fontWeight: 700 }}>{paidSources.length} STUB</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {paidSources.map(s => (
              <div key={s.name} style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", background: theme.surfaceAlt, borderRadius: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: theme.textFaint }} />
                  <span style={{ fontSize: 12, color: theme.textDim }}>{s.name}</span>
                </div>
                <button style={{ fontSize: 10, color: theme.accent, background: "transparent", border: "none", cursor: "pointer", fontFamily: "inherit" }}>Configure →</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── STUB VIEWS ─────────────────────────────────────────────────
function KBQStub({ theme }) {
  return <Stub theme={theme} icon="▦" title="KBQ Workspace" desc="Eight-station structured intelligence pipeline. KBQ-1 through KBQ-8 with sources, decision gates, and evidence-linked outputs. Full implementation in Helix prototype." />;
}
function WarGameStub({ theme }) {
  return <Stub theme={theme} icon="⚔" title="War Game" desc="Three modes — Manual, Auto-Simulate, Game-Theoretic (Nash + Stackelberg). Sessions called War Rooms. Full implementation in Helix prototype." />;
}
function KnowledgeStub({ theme }) {
  return <Stub theme={theme} icon="▤" title="Knowledge" desc="Internal document upload and indexing. Drop PDFs, decks, transcripts. Cited as INTERNAL:doc-id across the platform. Full implementation in Helix prototype." />;
}
function ReplayStub({ theme }) {
  return <Stub theme={theme} icon="↻" title="Replay" desc="Scrub through twin belief history. Markers for signals, moments, decisions. Insights from MarketZero folded in here. Full implementation in Helix prototype." />;
}

function Stub({ theme, icon, title, desc }) {
  return (
    <div className="fade-in" style={{ padding: 32 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: 36, letterSpacing: "-0.02em" }}>{title}</div>
        <div style={{ fontSize: 13, color: theme.textDim, marginTop: 6, maxWidth: 640, lineHeight: 1.6 }}>{desc}</div>
      </div>
      <div style={{ background: theme.surface, border: "1px solid " + theme.border, borderRadius: 12, padding: 60, textAlign: "center" }}>
        <div style={{ fontSize: 64, color: theme.accent, marginBottom: 16, opacity: 0.4 }}>{icon}</div>
        <div style={{ fontSize: 12, color: theme.textFaint, letterSpacing: "0.1em" }}>SURFACE EXISTS IN HELIX PROTOTYPE · IA INTEGRATION PENDING</div>
      </div>
    </div>
  );
}