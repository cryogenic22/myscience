import { useState, useRef, useEffect, useMemo } from "react";

// ─── HELPERS ────────────────────────────────────────────────────
function escapeRegex(s) {
  return s.replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");
}

// ─── CONFIG ─────────────────────────────────────────────────────
const DEFAULT_COMPANIES = [
  { id: "novo", name: "Novo Nordisk", color: "#003b71",
    knownDrugs: ["semaglutide", "Ozempic", "Wegovy", "Rybelsus", "liraglutide"] },
  { id: "lilly", name: "Eli Lilly", color: "#d52b1e",
    knownDrugs: ["tirzepatide", "Mounjaro", "Zepbound", "retatrutide", "orforglipron"] },
  { id: "amgen", name: "Amgen", color: "#0063c3",
    knownDrugs: ["MariTide", "AMG 133", "maridebart cafraglutide"] },
  { id: "pfizer", name: "Pfizer", color: "#0093d0",
    knownDrugs: ["danuglipron", "lotiglipron", "PF-07081532"] },
];

const PHASES = [
  { id: "prelaunch", label: "Pre-Launch", desc: "Phase 3 → approval" },
  { id: "launch", label: "Launch", desc: "First 12 months" },
  { id: "postlaunch", label: "Post-Launch", desc: "12-36 months" },
];

const MOVE_TYPES = [
  { id: "price_cut", label: "Price Cut", icon: "💵",
    fields: ["target_drug", "discount_pct", "geography", "timing"],
    desc: "Reduce list/net price on a product" },
  { id: "new_indication", label: "New Indication Launch", icon: "🎯",
    fields: ["target_drug", "indication", "phase", "timing"],
    desc: "Pursue new indication approval" },
  { id: "label_expansion", label: "Label Expansion", icon: "📋",
    fields: ["target_drug", "expansion", "evidence_source", "timing"],
    desc: "Expand existing label" },
  { id: "trial_readout", label: "Pivotal Trial Readout", icon: "📊",
    fields: ["target_drug", "trial_id", "endpoint", "timing"],
    desc: "Announce Phase 3 results" },
  { id: "acquisition", label: "Acquisition / In-License", icon: "🤝",
    fields: ["asset", "deal_size", "indication", "timing"],
    desc: "M&A or in-licensing" },
  { id: "formulation_switch", label: "Formulation Switch", icon: "💊",
    fields: ["target_drug", "new_formulation", "advantage", "timing"],
    desc: "Launch new formulation" },
  { id: "geo_expansion", label: "Geographic Expansion", icon: "🌍",
    fields: ["target_drug", "region", "approach", "timing"],
    desc: "Enter new geography" },
  { id: "segment_pivot", label: "Segment Pivot", icon: "🎯",
    fields: ["target_drug", "from_segment", "to_segment", "timing"],
    desc: "Shift between patient segments" },
];

const REACTION_TYPES = [
  { id: "match_price", label: "Match Price", color: "#f0883e" },
  { id: "counter_launch", label: "Counter-Launch", color: "#d52b1e" },
  { id: "accelerate_trial", label: "Accelerate Trial", color: "#a371f7" },
  { id: "seek_partnership", label: "Seek Partnership", color: "#3fb950" },
  { id: "attack_label", label: "Attack Label", color: "#f85149" },
  { id: "hold_position", label: "Hold Position", color: "#8b949e" },
  { id: "exit_segment", label: "Exit Segment", color: "#484f58" },
  { id: "differentiate", label: "Differentiate", color: "#58a6ff" },
];

const REACTION_DIMENSIONS = [
  { id: "market_share_delta", label: "Mkt Share Δ", unit: "%" },
  { id: "time_to_execute_months", label: "Time", unit: "mo" },
  { id: "capex_required_musd", label: "Capex", unit: "$M" },
  { id: "regulatory_risk", label: "Reg Risk", unit: "/10" },
  { id: "payer_acceptance", label: "Payer", unit: "/10" },
];

const SOURCES = [
  { id: "pubmed", label: "PubMed", icon: "🧬", color: "#1a7abf", desc: "Peer-reviewed literature" },
  { id: "biorxiv", label: "bioRxiv", icon: "📄", color: "#c0392b", desc: "Preprints" },
  { id: "chembl", label: "ChEMBL", icon: "⚗️", color: "#27ae60", desc: "Drug compounds & targets" },
  { id: "trials", label: "Clinical Trials", icon: "🏥", color: "#8e44ad", desc: "Active & completed trials" },
  { id: "icd10", label: "ICD-10", icon: "📋", color: "#e67e22", desc: "Diagnosis codes" },
  { id: "npi", label: "NPI Registry", icon: "👩‍⚕️", color: "#2c3e50", desc: "Healthcare providers" },
  { id: "cms", label: "CMS Coverage", icon: "📑", color: "#16a085", desc: "Medicare coverage policies" },
];

const SOURCE_MAP = {
  pubmed: "PubMed", biorxiv: "bioRxiv", chembl: "ChEMBL",
  trials: "Clinical Trials", icd10: "ICD-10 Codes", npi: "NPI Registry", cms: "CMS Coverage",
};

const MCP_SERVERS = {
  PubMed: "https://pubmed.mcp.claude.com/mcp",
  bioRxiv: "https://hcls.mcp.claude.com/biorxiv/mcp",
  ChEMBL: "https://hcls.mcp.claude.com/chembl/mcp",
  "Clinical Trials": "https://hcls.mcp.claude.com/clinical_trials/mcp",
  "ICD-10 Codes": "https://hcls.mcp.claude.com/icd10_codes/mcp",
  "NPI Registry": "https://hcls.mcp.claude.com/npi_registry/mcp",
  "CMS Coverage": "https://hcls.mcp.claude.com/cms_coverage/mcp",
};

// ─── API CALLS ──────────────────────────────────────────────────
async function callClaude(payload) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

function extractText(data) {
  return (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
}

function tryParseJSON(text) {
  const clean = text.replace(/```json|```/g, "").trim();
  try { return JSON.parse(clean); } catch {}
  const match = clean.match(/[\{\[][\s\S]*[\}\]]/);
  if (match) {
    try { return JSON.parse(match[0]); } catch {}
  }
  return null;
}

const SOURCE_PROMPTS = {
  pubmed: q => "Search PubMed for articles about \"" + q + "\". Return top 5 with title, authors, journal, year, summary. Use search_articles.",
  biorxiv: q => "Search bioRxiv for preprints about \"" + q + "\". Return top 5 with title, authors, date, summary. Use search_preprints.",
  chembl: q => "Search ChEMBL for drugs/compounds related to \"" + q + "\". Return up to 5 with name, ChEMBL ID, type, description. Use drug_search or compound_search.",
  trials: q => "Search ClinicalTrials.gov for trials about \"" + q + "\". Return top 5 with title, status, phase, sponsor. Use search_trials.",
  icd10: q => "Search ICD-10 codes for \"" + q + "\". Return up to 8 with code, description, category. Use search_codes.",
  npi: q => "Search NPI Registry providers for \"" + q + "\". Return up to 5 with name, specialty, location. Use npi_search.",
  cms: q => "Search CMS Medicare coverage for \"" + q + "\". Return up to 5 with title, type, description. Use search_national_coverage or search_local_coverage.",
};

async function querySource(sourceId, query) {
  const serverName = SOURCE_MAP[sourceId];
  const data = await callClaude({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1500,
    system: "Use MCP tools to search. Return JSON: {\"results\":[{\"title\",\"subtitle\",\"detail\",\"url\":optional,\"id\":optional}]}. ONLY JSON. No markdown.",
    messages: [{ role: "user", content: SOURCE_PROMPTS[sourceId](query) }],
    mcp_servers: [{ type: "url", url: MCP_SERVERS[serverName], name: serverName }],
  });
  const text = extractText(data);
  const parsed = tryParseJSON(text);
  if (parsed) return parsed.results || parsed;
  return [{ title: "Results retrieved", subtitle: "", detail: text.slice(0, 300) }];
}

async function extractEntities(query, allResults) {
  const corpus = [];
  Object.entries(allResults).forEach(([sourceId, results]) => {
    if (!Array.isArray(results)) return;
    results.forEach((r, i) => {
      corpus.push({ sourceId, resultIndex: i, title: r.title || "", subtitle: r.subtitle || "", detail: r.detail || "" });
    });
  });
  const data = await callClaude({
    model: "claude-sonnet-4-20250514",
    max_tokens: 2000,
    system: "Extract biomedical entities ONLY if they appear verbatim in the corpus. Each entity needs provenance. Categorize: drug, gene, condition, code, provider, trial, organization. Return: {\"entities\":[{\"name\",\"type\",\"provenance\":[{\"sourceId\",\"resultIndex\"}]}]}. Max 20. ONLY JSON.",
    messages: [{ role: "user", content: "Query: \"" + query + "\"\n\nCorpus:\n" + JSON.stringify(corpus, null, 2) }],
  });
  const parsed = tryParseJSON(extractText(data));
  return (parsed && parsed.entities) || [];
}

async function synthesize(query, allResults) {
  const corpus = [];
  Object.entries(allResults).forEach(([sourceId, results]) => {
    if (!Array.isArray(results)) return;
    results.forEach((r, i) => {
      corpus.push({ sourceId, resultIndex: i, title: r.title, subtitle: r.subtitle, detail: r.detail });
    });
  });
  const data = await callClaude({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1500,
    system: "Synthesize results. EVERY claim must cite [sourceId:resultIndex]. No unsupported claims. 3-5 paragraphs: overview, findings, context, gaps. Plain text with inline citations like [pubmed:0].",
    messages: [{ role: "user", content: "Query: \"" + query + "\"\n\nCorpus:\n" + JSON.stringify(corpus, null, 2) }],
  });
  return extractText(data);
}

async function buildDossier(company) {
  const dossier = { company: company.name, trials: [], pubs: [], compounds: [] };
  const drugs = company.knownDrugs.join(", ");

  try {
    const data = await callClaude({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1500,
      system: "Use search_by_sponsor. Return ONLY JSON: {\"trials\":[{\"nct\",\"title\",\"status\",\"phase\",\"indication\"}]}. Limit 8.",
      messages: [{ role: "user", content: "Find GLP-1 / obesity / T2D trials sponsored by " + company.name + "." }],
      mcp_servers: [{ type: "url", url: MCP_SERVERS["Clinical Trials"], name: "Clinical Trials" }],
    });
    const parsed = tryParseJSON(extractText(data));
    if (parsed && parsed.trials) dossier.trials = parsed.trials.slice(0, 8);
  } catch {}

  try {
    const data = await callClaude({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1200,
      system: "Use search_articles. Return ONLY JSON: {\"pubs\":[{\"pmid\",\"title\",\"year\",\"key_finding\"}]}. Limit 6.",
      messages: [{ role: "user", content: "Find recent (2023-2026) publications about " + company.name + "'s GLP-1 programs. Drugs: " + drugs }],
      mcp_servers: [{ type: "url", url: MCP_SERVERS.PubMed, name: "PubMed" }],
    });
    const parsed = tryParseJSON(extractText(data));
    if (parsed && parsed.pubs) dossier.pubs = parsed.pubs.slice(0, 6);
  } catch {}

  try {
    const data = await callClaude({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      system: "Use drug_search/compound_search. Return ONLY JSON: {\"compounds\":[{\"name\",\"chembl_id\",\"mechanism\",\"phase\"}]}. Limit 5.",
      messages: [{ role: "user", content: "Find ChEMBL records for: " + drugs }],
      mcp_servers: [{ type: "url", url: MCP_SERVERS.ChEMBL, name: "ChEMBL" }],
    });
    const parsed = tryParseJSON(extractText(data));
    if (parsed && parsed.compounds) dossier.compounds = parsed.compounds.slice(0, 5);
  } catch {}

  return dossier;
}

async function runReactionTurn({ playerCompany, playerMove, competitor, dossier, allDossiers, history, roundNumber }) {
  const moveType = MOVE_TYPES.find(m => m.id === playerMove.type);
  const otherDossiers = Object.entries(allDossiers)
    .filter(([id]) => id !== competitor.id && id !== playerCompany.id)
    .map(([, d]) => ({ company: d.company, trials: (d.trials || []).slice(0, 3), compounds: (d.compounds || []).slice(0, 3) }));

  const sysParts = [
    "You are a deterministic strategy engine playing as " + competitor.name + ".",
    playerCompany.name + " just executed a structured competitive move.",
    "",
    "GROUNDING RULES:",
    "1. Reaction must be derivable from competitor's dossier — pick the asset (NCT/CHEMBL/PMID) that best enables it.",
    "2. Every numeric score must be justified by dossier evidence.",
    "3. If no asset enables a credible reaction, choose hold_position. Do NOT invent capabilities.",
    "4. Be deterministic and conservative.",
    "",
    "REACTION ENUM: match_price | counter_launch | accelerate_trial | seek_partnership | attack_label | hold_position | exit_segment | differentiate",
    "",
    "SCORING (conservative):",
    "- market_share_delta: -10 to +10 (% pts; positive = " + competitor.name + " gains)",
    "- time_to_execute_months: 1-36",
    "- capex_required_musd: 50-3000",
    "- regulatory_risk: 1-10 (10 highest)",
    "- payer_acceptance: 1-10 (10 strongest)",
    "",
    "Output ONLY JSON:",
    "{",
    "  \"company\": \"" + competitor.name + "\",",
    "  \"reaction_type\": \"<enum>\",",
    "  \"headline\": \"8-12 word headline\",",
    "  \"specific_action\": \"concrete action with target asset name\",",
    "  \"asset_leveraged\": { \"id\", \"name\", \"rationale\" },",
    "  \"rationale\": \"2-3 sentences citing dossier IDs\",",
    "  \"evidence_basis\": [\"NCT...\", \"PMID:...\", \"CHEMBL...\"],",
    "  \"scores\": { \"market_share_delta\", \"time_to_execute_months\", \"capex_required_musd\", \"regulatory_risk\", \"payer_acceptance\" },",
    "  \"confidence\": \"high|medium|low\",",
    "  \"ripple_target\": \"which competitor reacts next and how\"",
    "}",
    "No preamble. No markdown."
  ];

  const userContent = [
    "PLAYER MOVE (" + playerCompany.name + ", round " + roundNumber + "):",
    JSON.stringify({ type: moveType ? moveType.label : playerMove.type, ...playerMove }, null, 2),
    "",
    "YOUR DOSSIER (" + competitor.name + "):",
    JSON.stringify(dossier, null, 2),
    "",
    "OTHER COMPETITORS:",
    JSON.stringify(otherDossiers, null, 2),
    "",
    "RECENT HISTORY:",
    JSON.stringify(history.slice(-4), null, 2),
    "",
    "Generate " + competitor.name + "'s reaction. Pick from enum, ground in dossier, score conservatively."
  ].join("\n");

  const data = await callClaude({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1500,
    system: sysParts.join("\n"),
    messages: [{ role: "user", content: userContent }],
  });

  const parsed = tryParseJSON(extractText(data));
  if (parsed) return parsed;
  return {
    company: competitor.name, reaction_type: "hold_position",
    headline: "Holding position pending data", specific_action: "Monitor",
    asset_leveraged: { id: "n/a", name: "n/a", rationale: "Parse failed" },
    rationale: "Could not generate reaction.", evidence_basis: [],
    scores: { market_share_delta: 0, time_to_execute_months: 12, capex_required_musd: 100, regulatory_risk: 5, payer_acceptance: 5 },
    confidence: "low", ripple_target: ""
  };
}

async function generateBriefing(playerCompany, allDossiers, rounds) {
  const data = await callClaude({
    model: "claude-sonnet-4-20250514",
    max_tokens: 2000,
    system: "Write competitive intel briefing for " + playerCompany.name + ". 4 sections in plain text:\n1. EXECUTIVE SUMMARY (3-4 sentences)\n2. TOP 3 COMPETITIVE THREATS\n3. WHITESPACE OPPORTUNITIES\n4. RECOMMENDED NEXT MOVES FOR " + playerCompany.name.toUpperCase() + "\nCite NCT/PMID/CHEMBL IDs from dossiers. No markdown headers — plain text labels.",
    messages: [{ role: "user", content: "DOSSIERS:\n" + JSON.stringify(allDossiers, null, 2) + "\n\nROUNDS:\n" + JSON.stringify(rounds, null, 2) }],
  });
  return extractText(data);
}

// ─── MAIN COMPONENT ─────────────────────────────────────────────
export default function App() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [errors, setErrors] = useState({});
  const [active, setActive] = useState(null);
  const [tab, setTab] = useState("sources");
  const [history, setHistory] = useState([]);
  const [entities, setEntities] = useState([]);
  const [entitiesLoading, setEntitiesLoading] = useState(false);
  const [synthText, setSynthText] = useState("");
  const [synthLoading, setSynthLoading] = useState(false);
  const [hoveredEntity, setHoveredEntity] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(true);

  // War game
  const [companies] = useState(DEFAULT_COMPANIES);
  const [playerId, setPlayerId] = useState("novo");
  const [phase, setPhase] = useState("prelaunch");
  const [dossiers, setDossiers] = useState({});
  const [dossierLoading, setDossierLoading] = useState({});
  const [rounds, setRounds] = useState([]);
  const [running, setRunning] = useState(false);
  const [visualMode, setVisualMode] = useState("flow");
  const [briefing, setBriefing] = useState("");
  const [briefingLoading, setBriefingLoading] = useState(false);

  const inputRef = useRef();

  useEffect(() => {
    (async () => {
      try {
        const list = await window.storage.list("history:");
        if (list && list.keys && list.keys.length) {
          const items = [];
          for (const k of list.keys) {
            try {
              const r = await window.storage.get(k);
              if (r && r.value) items.push(JSON.parse(r.value));
            } catch {}
          }
          items.sort((a, b) => b.ts - a.ts);
          setHistory(items.slice(0, 20));
        }
      } catch {}
    })();
  }, []);

  const saveHistory = async (q, res) => {
    const counts = {};
    Object.entries(res).forEach(([k, v]) => { counts[k] = Array.isArray(v) ? v.length : 0; });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const entry = { query: q, ts: Date.now(), counts, total };
    try {
      await window.storage.set("history:" + entry.ts, JSON.stringify(entry));
      setHistory(prev => [entry, ...prev].slice(0, 20));
    } catch {}
  };

  const handleSearch = async (override) => {
    const q = (override !== undefined ? override : query).trim();
    if (!q) return;
    setQuery(q);
    setSubmitted(q);
    setResults({});
    setErrors({});
    setActive(null);
    setEntities([]);
    setSynthText("");
    setTab("sources");
    const ls = {};
    SOURCES.forEach(s => { ls[s.id] = true; });
    setLoading(ls);

    const collected = {};
    await Promise.all(SOURCES.map(async source => {
      try {
        const data = await querySource(source.id, q);
        collected[source.id] = data;
        setResults(prev => ({ ...prev, [source.id]: data }));
      } catch (e) {
        setErrors(prev => ({ ...prev, [source.id]: e.message }));
      } finally {
        setLoading(prev => ({ ...prev, [source.id]: false }));
      }
    }));

    if (Object.keys(collected).length > 0) {
      saveHistory(q, collected);
      setEntitiesLoading(true);
      setSynthLoading(true);
      extractEntities(q, collected).then(setEntities).catch(() => setEntities([])).finally(() => setEntitiesLoading(false));
      synthesize(q, collected).then(setSynthText).catch(() => setSynthText("Synthesis unavailable.")).finally(() => setSynthLoading(false));
    }
  };

  const buildAllDossiers = async () => {
    const init = {};
    companies.forEach(c => { init[c.id] = true; });
    setDossierLoading(init);
    const out = {};
    await Promise.all(companies.map(async c => {
      try {
        const d = await buildDossier(c);
        out[c.id] = d;
        setDossiers(prev => ({ ...prev, [c.id]: d }));
      } catch (e) {
        out[c.id] = { company: c.name, trials: [], pubs: [], compounds: [], error: e.message };
      } finally {
        setDossierLoading(prev => ({ ...prev, [c.id]: false }));
      }
    }));
    return out;
  };

  const playMove = async (moveSpec) => {
    setRunning(true);
    setBriefing("");

    let dossiersNow = dossiers;
    if (Object.keys(dossiersNow).length < companies.length) {
      dossiersNow = await buildAllDossiers();
    }

    const playerCo = companies.find(c => c.id === playerId);
    const competitors = companies.filter(c => c.id !== playerId);
    const roundNumber = rounds.length + 1;
    const fullHistory = rounds.flatMap(r => [
      { type: "player_move", company: r.playerCompany, ...r.playerMove },
      ...r.reactions.map(rx => ({ type: "reaction", ...rx }))
    ]);

    const reactions = await Promise.all(competitors.map(c =>
      runReactionTurn({
        playerCompany: playerCo, playerMove: moveSpec, competitor: c,
        dossier: dossiersNow[c.id], allDossiers: dossiersNow,
        history: fullHistory, roundNumber,
      })
    ));

    const newRound = {
      roundNumber,
      playerMove: moveSpec,
      playerCompany: playerCo.name,
      playerColor: playerCo.color,
      reactions,
    };
    setRounds(prev => [...prev, newRound]);
    setRunning(false);
  };

  const finalizeBriefing = async () => {
    setBriefingLoading(true);
    try {
      const playerCo = companies.find(c => c.id === playerId);
      const text = await generateBriefing(playerCo, dossiers, rounds);
      setBriefing(text);
    } catch (e) {
      setBriefing("Briefing failed: " + e.message);
    } finally {
      setBriefingLoading(false);
    }
  };

  const resetWar = () => {
    setRounds([]);
    setBriefing("");
  };

  const totalResults = Object.values(results).reduce((s, r) => s + (Array.isArray(r) ? r.length : 0), 0);
  const allDone = submitted && SOURCES.every(s => !loading[s.id]);
  const activeSource = active ? SOURCES.find(s => s.id === active) : null;
  const activeResults = active ? results[active] : null;

  const exportJSON = () => {
    const payload = { query: submitted, ts: new Date().toISOString(), results, entities, synthesis: synthText };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "medsearch-" + submitted.replace(/\s+/g, "_") + ".json"; a.click();
    URL.revokeObjectURL(url);
  };

  const exportCSV = () => {
    const rows = [["source", "title", "subtitle", "detail", "id_or_url"]];
    Object.entries(results).forEach(([sid, arr]) => {
      if (!Array.isArray(arr)) return;
      arr.forEach(r => {
        rows.push([
          SOURCE_MAP[sid] || sid,
          (r.title || "").replace(/"/g, '""'),
          (r.subtitle || "").replace(/"/g, '""'),
          (r.detail || "").replace(/"/g, '""'),
          (r.url || r.id || "").toString(),
        ]);
      });
    });
    const csv = rows.map(row => row.map(c => '"' + c + '"').join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "medsearch-" + submitted.replace(/\s+/g, "_") + ".csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const renderSynthesis = (text) => {
    if (!text) return null;
    const parts = text.split(/(\[[a-z0-9]+:\d+\])/gi);
    return parts.map((part, i) => {
      const m = part.match(/^\[([a-z0-9]+):(\d+)\]$/i);
      if (m) {
        const sid = m[1].toLowerCase();
        const idx = parseInt(m[2], 10);
        const src = SOURCES.find(s => s.id === sid);
        if (src) {
          return (
            <span key={i} onClick={() => { setActive(sid); setTab("sources"); }}
              style={{ display: "inline-block", padding: "1px 8px", margin: "0 2px", borderRadius: 10, fontSize: 10, fontWeight: 600, background: src.color + "25", color: src.color, border: "1px solid " + src.color + "50", cursor: "pointer", fontFamily: "'DM Mono', monospace" }}>
              {src.icon} {src.label.toUpperCase()}:{idx}
            </span>
          );
        }
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0d1117", fontFamily: "'DM Mono', 'Fira Code', monospace", color: "#e6edf3", display: "flex" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #161b22; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
        .pulse { animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
        .fade-in { animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; } }
        .card-hover { transition: all 0.2s ease; cursor: pointer; }
        .card-hover:hover { transform: translateY(-2px); }
        .tab-btn { background: transparent; border: none; padding: 10px 18px; color: #8b949e; cursor: pointer; font-family: inherit; font-size: 12px; letter-spacing: 0.05em; border-bottom: 2px solid transparent; }
        .tab-btn.active { color: #e6edf3; border-bottom-color: #58a6ff; }
        .tab-btn:hover { color: #e6edf3; }
        .history-item:hover { background: #1c2128 !important; }
        .search-input:focus { outline: none; border-color: #58a6ff !important; box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
        @media (max-width: 768px) { .sidebar { display: none !important; } }
      `}</style>

      {historyOpen && (
        <div className="sidebar" style={{ width: 240, borderRight: "1px solid #21262d", background: "#0a0d12", padding: "20px 16px", display: "flex", flexDirection: "column", gap: 12, minHeight: "100vh", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 11, color: "#8b949e", letterSpacing: "0.1em" }}>HISTORY</div>
          </div>
          {history.length === 0 ? (
            <div style={{ fontSize: 11, color: "#484f58", lineHeight: 1.5 }}>No searches yet.</div>
          ) : history.map(h => (
            <div key={h.ts} className="history-item" onClick={() => handleSearch(h.query)}
              style={{ padding: "10px 12px", borderRadius: 6, background: "#161b22", border: "1px solid #21262d", cursor: "pointer" }}>
              <div style={{ fontSize: 12, color: "#e6edf3", fontWeight: 500, marginBottom: 4, wordBreak: "break-word" }}>{h.query}</div>
              <div style={{ fontSize: 10, color: "#8b949e", display: "flex", justifyContent: "space-between" }}>
                <span>{h.total} results</span>
                <span>{new Date(h.ts).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ borderBottom: "1px solid #21262d", padding: "20px 32px", display: "flex", alignItems: "center", gap: 16 }}>
          <button onClick={() => setHistoryOpen(!historyOpen)} style={{ background: "transparent", border: "1px solid #30363d", borderRadius: 6, padding: "6px 10px", color: "#8b949e", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>≡</button>
          <div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 22, fontWeight: 800, letterSpacing: "-0.5px" }}>
              MED<span style={{ color: "#58a6ff" }}>SEARCH</span>
            </div>
            <div style={{ fontSize: 11, color: "#8b949e", marginTop: 2 }}>unified biomedical intelligence · grounded · war-gaming</div>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            {SOURCES.map(s => {
              let bg = "#30363d";
              if (submitted) {
                if (loading[s.id]) bg = "#f0883e";
                else if (errors[s.id]) bg = "#f85149";
                else if (results[s.id]) bg = "#3fb950";
                else bg = "#8b949e";
              }
              return <div key={s.id} style={{ width: 8, height: 8, borderRadius: "50%", background: bg }} title={s.label} />;
            })}
          </div>
        </div>

        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
          <div style={{ marginBottom: 32 }}>
            <div style={{ fontSize: 13, color: "#8b949e", marginBottom: 12, letterSpacing: "0.05em" }}>QUERY → 7 SOURCES</div>
            <div style={{ display: "flex", gap: 12 }}>
              <input ref={inputRef} className="search-input" value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                placeholder="e.g. metformin, BRCA1, GLP-1..."
                style={{ flex: 1, background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: "14px 18px", fontSize: 15, color: "#e6edf3", fontFamily: "inherit" }} />
              <button onClick={() => handleSearch()} disabled={!query.trim() || Object.values(loading).some(Boolean)}
                style={{ background: "#1f6feb", border: "none", borderRadius: 8, padding: "14px 28px", color: "#fff", fontSize: 13, fontFamily: "inherit", fontWeight: 500, cursor: "pointer", letterSpacing: "0.05em", opacity: (!query.trim() || Object.values(loading).some(Boolean)) ? 0.5 : 1 }}>
                {Object.values(loading).some(Boolean) ? "SEARCHING..." : "SEARCH →"}
              </button>
            </div>
          </div>

          {submitted && (
            <div style={{ borderBottom: "1px solid #21262d", marginBottom: 24, display: "flex", gap: 4, flexWrap: "wrap" }}>
              <button className={"tab-btn " + (tab === "sources" ? "active" : "")} onClick={() => setTab("sources")}>SOURCES</button>
              <button className={"tab-btn " + (tab === "graph" ? "active" : "")} onClick={() => setTab("graph")}>GRAPH {entitiesLoading ? "·" : entities.length > 0 ? "· " + entities.length : ""}</button>
              <button className={"tab-btn " + (tab === "synthesis" ? "active" : "")} onClick={() => setTab("synthesis")}>SYNTHESIS {synthLoading ? "·" : synthText ? "✓" : ""}</button>
              <button className={"tab-btn " + (tab === "wargame" ? "active" : "")} onClick={() => setTab("wargame")}>⚔ WAR GAME</button>
              <button className={"tab-btn " + (tab === "export" ? "active" : "")} onClick={() => setTab("export")}>EXPORT</button>
            </div>
          )}

          {!submitted && (
            <div style={{ marginBottom: 24, display: "flex", justifyContent: "center" }}>
              <button onClick={() => setTab("wargame")} style={{
                background: tab === "wargame" ? "#1f6feb" : "#161b22",
                border: "1px solid " + (tab === "wargame" ? "#1f6feb" : "#30363d"),
                borderRadius: 8, padding: "10px 24px", color: tab === "wargame" ? "#fff" : "#e6edf3",
                cursor: "pointer", fontFamily: "inherit", fontSize: 12, letterSpacing: "0.05em",
              }}>⚔ ENTER WAR GAME</button>
            </div>
          )}

          {tab === "sources" && active && activeSource && (
            <div className="fade-in" style={{ marginBottom: 32, background: "#161b22", border: "1px solid " + activeSource.color + "40", borderRadius: 12, padding: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
                <button onClick={() => setActive(null)} style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "6px 14px", color: "#8b949e", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>← BACK</button>
                <span style={{ fontSize: 20 }}>{activeSource.icon}</span>
                <span style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, color: activeSource.color }}>{activeSource.label}</span>
                <span style={{ fontSize: 12, color: "#8b949e" }}>{activeSource.desc}</span>
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#8b949e" }}>{(activeResults || []).length} results</span>
              </div>
              {loading[active] ? <div className="pulse" style={{ color: "#8b949e", fontSize: 13 }}>Fetching...</div>
                : errors[active] ? <div style={{ color: "#f85149", fontSize: 13 }}>Error: {errors[active]}</div>
                : Array.isArray(activeResults) && activeResults.length > 0 ? activeResults.map((r, i) => (
                  <div key={i} className="fade-in" style={{ borderBottom: "1px solid #21262d", padding: "12px 0" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                      <span style={{ fontSize: 10, color: activeSource.color, fontWeight: 600, fontFamily: "'DM Mono', monospace" }}>[{i}]</span>
                      <div style={{ fontSize: 14, color: "#e6edf3", fontWeight: 500, lineHeight: 1.4 }}>{r.title}</div>
                    </div>
                    {r.subtitle && <div style={{ fontSize: 12, color: activeSource.color, marginBottom: 4, marginLeft: 24 }}>{r.subtitle}</div>}
                    {r.detail && <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.5, marginLeft: 24 }}>{r.detail}</div>}
                  </div>
                )) : <div style={{ color: "#8b949e", fontSize: 13 }}>No results.</div>}
            </div>
          )}

          {tab === "sources" && !active && submitted && (
            <>
              <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 20, letterSpacing: "0.05em" }}>
                {allDone ? "SEARCH COMPLETE — " + totalResults + " RESULTS" : "SEARCHING " + Object.values(loading).filter(Boolean).length + " SOURCES..."}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16 }}>
                {SOURCES.map(source => {
                  const isLoading = loading[source.id];
                  const hasError = errors[source.id];
                  const res = results[source.id];
                  const count = Array.isArray(res) ? res.length : 0;
                  let borderColor = "#21262d";
                  if (isLoading) borderColor = "#f0883e40";
                  else if (hasError) borderColor = "#f8514940";
                  else if (res) borderColor = source.color + "40";
                  return (
                    <div key={source.id} className="card-hover fade-in"
                      onClick={() => !isLoading && setActive(source.id)}
                      style={{ background: "#161b22", border: "1px solid " + borderColor, borderRadius: 10, padding: "18px 20px", opacity: isLoading ? 0.8 : 1 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 18 }}>{source.icon}</span>
                          <span style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13, color: source.color }}>{source.label}</span>
                        </div>
                        {isLoading && <div className="pulse" style={{ width: 8, height: 8, borderRadius: "50%", background: "#f0883e" }} />}
                        {!isLoading && res && <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#3fb950" }} />}
                        {!isLoading && hasError && <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#f85149" }} />}
                      </div>
                      <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 12 }}>{source.desc}</div>
                      {isLoading && <div className="pulse" style={{ fontSize: 12, color: "#8b949e" }}>Searching...</div>}
                      {hasError && <div style={{ fontSize: 12, color: "#f85149" }}>Failed</div>}
                      {res && !isLoading && (
                        <>
                          <div style={{ fontSize: 22, fontFamily: "'Syne', sans-serif", fontWeight: 800, color: source.color, marginBottom: 4 }}>{count}</div>
                          <div style={{ fontSize: 11, color: "#8b949e" }}>
                            {Array.isArray(res) && res[0] && res[0].title ? (res[0].title.length > 60 ? res[0].title.slice(0, 60) + "..." : res[0].title) : "results"}
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {tab === "graph" && submitted && (
            <GraphView query={submitted} entities={entities} loading={entitiesLoading} results={results}
              hoveredEntity={hoveredEntity} setHoveredEntity={setHoveredEntity}
              onJumpToSource={(sid) => { setActive(sid); setTab("sources"); }} />
          )}

          {tab === "synthesis" && submitted && (
            <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Cross-Source Synthesis</div>
              <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 20 }}>Click a source badge to jump to the result.</div>
              {synthLoading ? <div className="pulse" style={{ color: "#8b949e" }}>Generating...</div>
                : synthText ? <div style={{ fontSize: 14, lineHeight: 1.8, whiteSpace: "pre-wrap" }}>{renderSynthesis(synthText)}</div>
                : <div style={{ color: "#8b949e" }}>No synthesis yet.</div>}
            </div>
          )}

          {tab === "wargame" && (
            <WarGamePanel
              companies={companies} playerId={playerId} setPlayerId={setPlayerId}
              phase={phase} setPhase={setPhase}
              dossiers={dossiers} dossierLoading={dossierLoading}
              buildAllDossiers={buildAllDossiers}
              rounds={rounds} running={running} playMove={playMove}
              visualMode={visualMode} setVisualMode={setVisualMode}
              briefing={briefing} briefingLoading={briefingLoading}
              finalizeBriefing={finalizeBriefing} resetWar={resetWar}
            />
          )}

          {tab === "export" && submitted && (
            <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Export</div>
              <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 24 }}>Download data for "{submitted}"</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16 }}>
                <button onClick={exportJSON} className="card-hover" style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 10, padding: 20, color: "#e6edf3", cursor: "pointer", fontFamily: "inherit", textAlign: "left" }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📦</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>JSON</div>
                  <div style={{ fontSize: 11, color: "#8b949e" }}>Full payload</div>
                </button>
                <button onClick={exportCSV} className="card-hover" style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 10, padding: 20, color: "#e6edf3", cursor: "pointer", fontFamily: "inherit", textAlign: "left" }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>CSV</div>
                  <div style={{ fontSize: 11, color: "#8b949e" }}>Flat table</div>
                </button>
              </div>
            </div>
          )}

          {!submitted && tab !== "wargame" && (
            <div style={{ textAlign: "center", padding: "60px 0", color: "#8b949e" }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🔬</div>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 700, color: "#e6edf3", marginBottom: 8 }}>Search 7 sources or enter the war room</div>
              <div style={{ fontSize: 13, maxWidth: 480, margin: "0 auto", lineHeight: 1.6 }}>
                Live MCP retrieval. Extracted entities. Grounded synthesis. Multi-agent simulation.
              </div>
              <div style={{ marginTop: 32, display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                {["metformin", "BRCA1", "GLP-1", "tirzepatide"].map(ex => (
                  <button key={ex} onClick={() => { setQuery(ex); setTimeout(() => inputRef.current && inputRef.current.focus(), 50); }}
                    style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 20, padding: "6px 16px", color: "#8b949e", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>{ex}</button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── WAR GAME PANEL ────────────────────────────────────────────
function WarGamePanel({ companies, playerId, setPlayerId, phase, setPhase, dossiers, dossierLoading, buildAllDossiers, rounds, running, playMove, visualMode, setVisualMode, briefing, briefingLoading, finalizeBriefing, resetWar }) {
  const [view, setView] = useState("setup");
  const playerCo = companies.find(c => c.id === playerId);
  const playerDossier = dossiers[playerId];
  const dossierCount = Object.keys(dossiers).length;
  const dossiersReady = dossierCount === companies.length && Object.values(dossierLoading).every(v => !v);
  const anyLoading = Object.values(dossierLoading).some(Boolean);

  return (
    <div className="fade-in">
      <div style={{ background: "linear-gradient(135deg, #161b22 0%, #1c2128 100%)", border: "1px solid #30363d", borderRadius: 12, padding: 24, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 28 }}>⚔</span>
          <div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 22, letterSpacing: "-0.5px" }}>GLP-1 WAR ROOM</div>
            <div style={{ fontSize: 11, color: "#8b949e", marginTop: 2 }}>structured moves · deterministic reactions · dossier-grounded</div>
          </div>
          {rounds.length > 0 && (
            <button onClick={resetWar} style={{ marginLeft: "auto", background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "6px 14px", color: "#8b949e", cursor: "pointer", fontSize: 11, fontFamily: "inherit" }}>↺ RESET</button>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 16, flexWrap: "wrap" }}>
          {[
            { id: "setup", label: "1. SETUP" },
            { id: "dossiers", label: "2. DOSSIERS" + (dossierCount > 0 ? " (" + dossierCount + ")" : "") },
            { id: "play", label: "3. PLAY" + (rounds.length > 0 ? " · R" + rounds.length : "") },
            { id: "briefing", label: "4. BRIEFING" },
          ].map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              background: view === v.id ? "#1f6feb" : "transparent",
              border: "1px solid " + (view === v.id ? "#1f6feb" : "#30363d"),
              borderRadius: 6, padding: "6px 14px", color: view === v.id ? "#fff" : "#8b949e",
              cursor: "pointer", fontFamily: "inherit", fontSize: 11, letterSpacing: "0.05em",
            }}>{v.label}</button>
          ))}
        </div>
      </div>

      {view === "setup" && (
        <div style={{ display: "grid", gap: 16 }}>
          <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 24 }}>
            <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 12, letterSpacing: "0.05em" }}>YOU PLAY AS · OTHERS REACT AS AGENTS</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
              {companies.map(c => (
                <div key={c.id} onClick={() => setPlayerId(c.id)} style={{
                  background: playerId === c.id ? c.color + "20" : "#0d1117",
                  border: "2px solid " + (playerId === c.id ? c.color : "#21262d"),
                  borderRadius: 8, padding: 14, cursor: "pointer",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, color: c.color }}>{c.name}</div>
                    {playerId === c.id && <div style={{ fontSize: 10, background: c.color, color: "#fff", padding: "2px 8px", borderRadius: 10, fontWeight: 600 }}>YOU</div>}
                  </div>
                  <div style={{ fontSize: 10, color: "#8b949e", lineHeight: 1.5 }}>{c.knownDrugs.slice(0, 3).join(" · ")}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 24 }}>
            <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 12, letterSpacing: "0.05em" }}>MARKET PHASE</div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {PHASES.map(p => (
                <button key={p.id} onClick={() => setPhase(p.id)} style={{
                  background: phase === p.id ? "#1f6feb20" : "#0d1117",
                  border: "1px solid " + (phase === p.id ? "#1f6feb" : "#30363d"),
                  borderRadius: 8, padding: "12px 18px", color: phase === p.id ? "#58a6ff" : "#e6edf3",
                  cursor: "pointer", fontFamily: "inherit", textAlign: "left", flex: "1 1 200px",
                }}>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 13 }}>{p.label}</div>
                  <div style={{ fontSize: 10, color: "#8b949e", marginTop: 3 }}>{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button onClick={async () => { await buildAllDossiers(); setView("dossiers"); }} disabled={anyLoading}
              style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 8, padding: "14px 24px", color: "#e6edf3", cursor: "pointer", fontFamily: "inherit", fontSize: 12, letterSpacing: "0.05em", flex: "1 1 240px", opacity: anyLoading ? 0.5 : 1 }}>
              {anyLoading ? "BUILDING DOSSIERS..." : "📁 BUILD DOSSIERS FROM REAL DATA"}
            </button>
            <button onClick={() => setView("play")} disabled={!dossiersReady}
              style={{ background: dossiersReady ? "#1f6feb" : "#30363d", border: "none", borderRadius: 8, padding: "14px 24px", color: "#fff", cursor: dossiersReady ? "pointer" : "not-allowed", fontFamily: "inherit", fontSize: 12, fontWeight: 600, letterSpacing: "0.05em", flex: "1 1 240px", opacity: dossiersReady ? 1 : 0.5 }}>
              ⚔ ENTER PLAY ROOM →
            </button>
          </div>
          <div style={{ fontSize: 10, color: "#484f58", textAlign: "center", lineHeight: 1.6 }}>
            Dossiers ground every reaction. Build first, then play.
          </div>
        </div>
      )}

      {view === "dossiers" && <DossierView companies={companies} dossiers={dossiers} dossierLoading={dossierLoading} playerId={playerId} />}

      {view === "play" && (
        <PlayRoom companies={companies} playerCo={playerCo} playerDossier={playerDossier}
          rounds={rounds} running={running} playMove={playMove}
          visualMode={visualMode} setVisualMode={setVisualMode} />
      )}

      {view === "briefing" && (
        <BriefingView companies={companies} playerCo={playerCo} rounds={rounds}
          briefing={briefing} briefingLoading={briefingLoading}
          finalizeBriefing={finalizeBriefing} dossierCount={dossierCount} />
      )}
    </div>
  );
}

// ─── DOSSIER VIEW ──────────────────────────────────────────────
function DossierView({ companies, dossiers, dossierLoading, playerId }) {
  if (Object.keys(dossiers).length === 0) {
    return (
      <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 40, textAlign: "center", color: "#8b949e", fontSize: 13 }}>
        No dossiers yet. Go to setup and click "Build Dossiers".
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {companies.map(c => {
        const d = dossiers[c.id];
        const isLoading = dossierLoading[c.id];
        return (
          <div key={c.id} style={{ background: "#161b22", border: "1px solid " + c.color + "40", borderRadius: 12, padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              <div style={{ width: 12, height: 12, borderRadius: "50%", background: c.color }} />
              <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, color: c.color }}>{c.name}</div>
              {playerId === c.id && <div style={{ fontSize: 9, background: c.color, color: "#fff", padding: "2px 6px", borderRadius: 8 }}>PLAYER</div>}
              {isLoading && <div className="pulse" style={{ fontSize: 10, color: "#f0883e", marginLeft: "auto" }}>LOADING...</div>}
              {d && !isLoading && (
                <div style={{ marginLeft: "auto", fontSize: 10, color: "#8b949e" }}>
                  {(d.trials || []).length} trials · {(d.pubs || []).length} pubs · {(d.compounds || []).length} compounds
                </div>
              )}
            </div>
            {d && !isLoading && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
                <DossierColumn title="🏥 TRIALS" items={(d.trials || []).slice(0, 4)} renderItem={(t, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#c9d1d9", padding: "6px 0", borderBottom: "1px solid #21262d" }}>
                    <div style={{ color: "#58a6ff", fontFamily: "'DM Mono', monospace", fontSize: 10 }}>{t.nct}</div>
                    <div style={{ marginTop: 2 }}>{t.title ? (t.title.length > 60 ? t.title.slice(0, 60) + "..." : t.title) : ""}</div>
                    <div style={{ fontSize: 10, color: "#8b949e", marginTop: 2 }}>{t.phase} · {t.status}</div>
                  </div>
                )} />
                <DossierColumn title="🧬 PUBS" items={(d.pubs || []).slice(0, 4)} renderItem={(p, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#c9d1d9", padding: "6px 0", borderBottom: "1px solid #21262d" }}>
                    <div style={{ color: "#58a6ff", fontFamily: "'DM Mono', monospace", fontSize: 10 }}>PMID:{p.pmid}</div>
                    <div style={{ marginTop: 2 }}>{p.title ? (p.title.length > 60 ? p.title.slice(0, 60) + "..." : p.title) : ""}</div>
                  </div>
                )} />
                <DossierColumn title="⚗️ COMPOUNDS" items={(d.compounds || []).slice(0, 4)} renderItem={(cmp, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#c9d1d9", padding: "6px 0", borderBottom: "1px solid #21262d" }}>
                    <div style={{ color: "#58a6ff", fontFamily: "'DM Mono', monospace", fontSize: 10 }}>{cmp.chembl_id}</div>
                    <div style={{ marginTop: 2, fontWeight: 500 }}>{cmp.name}</div>
                    <div style={{ fontSize: 10, color: "#8b949e", marginTop: 2 }}>{cmp.mechanism}</div>
                  </div>
                )} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DossierColumn({ title, items, renderItem }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "#8b949e", marginBottom: 6, letterSpacing: "0.05em" }}>{title}</div>
      {items.map(renderItem)}
    </div>
  );
}

// ─── PLAY ROOM ─────────────────────────────────────────────────
function PlayRoom({ companies, playerCo, playerDossier, rounds, running, playMove, visualMode, setVisualMode }) {
  const [showBuilder, setShowBuilder] = useState(rounds.length === 0);

  return (
    <div>
      <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 16, marginBottom: 16, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontSize: 11, color: "#8b949e", letterSpacing: "0.05em" }}>VIEW:</div>
        {[{ id: "flow", label: "🔀 FLOW" }, { id: "matrix", label: "▦ MATRIX" }].map(m => (
          <button key={m.id} onClick={() => setVisualMode(m.id)} style={{
            background: visualMode === m.id ? "#1f6feb" : "#0d1117",
            border: "1px solid " + (visualMode === m.id ? "#1f6feb" : "#30363d"),
            borderRadius: 6, padding: "6px 12px", color: visualMode === m.id ? "#fff" : "#8b949e",
            cursor: "pointer", fontFamily: "inherit", fontSize: 11,
          }}>{m.label}</button>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 11, color: "#8b949e" }}>
          {rounds.length} round{rounds.length !== 1 ? "s" : ""} · playing as <span style={{ color: playerCo.color, fontWeight: 600 }}>{playerCo.name}</span>
        </div>
      </div>

      {!running && (showBuilder || rounds.length === 0) && (
        <MoveBuilder playerCo={playerCo} playerDossier={playerDossier}
          onSubmit={move => { playMove(move); setShowBuilder(false); }}
          roundNumber={rounds.length + 1} />
      )}

      {!running && !showBuilder && rounds.length > 0 && (
        <button onClick={() => setShowBuilder(true)} style={{
          width: "100%", background: playerCo.color + "15", border: "1px dashed " + playerCo.color,
          borderRadius: 12, padding: "20px", color: playerCo.color, cursor: "pointer",
          fontFamily: "inherit", fontSize: 13, marginBottom: 16, fontWeight: 600,
        }}>
          ＋ EXECUTE NEXT MOVE (ROUND {rounds.length + 1})
        </button>
      )}

      {running && (
        <div style={{ background: "#161b22", border: "1px solid #f0883e40", borderRadius: 12, padding: 30, textAlign: "center", marginBottom: 16 }}>
          <div className="pulse" style={{ fontSize: 14, color: "#f0883e", marginBottom: 6 }}>⚔ Competitors deliberating...</div>
          <div style={{ fontSize: 11, color: "#8b949e" }}>Each agent picking a reaction grounded in their dossier</div>
        </div>
      )}

      {[...rounds].reverse().map(round => (
        visualMode === "flow"
          ? <FlowDiagram key={round.roundNumber} round={round} companies={companies} />
          : <ReactionMatrix key={round.roundNumber} round={round} companies={companies} />
      ))}

      {rounds.length === 0 && !running && !showBuilder && (
        <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 40, textAlign: "center", color: "#8b949e", fontSize: 13 }}>
          Build a move above to start.
        </div>
      )}
    </div>
  );
}

// ─── MOVE BUILDER ──────────────────────────────────────────────
function MoveBuilder({ playerCo, playerDossier, onSubmit, roundNumber }) {
  const [moveType, setMoveType] = useState(null);
  const [fields, setFields] = useState({});

  const trials = (playerDossier && playerDossier.trials) || [];
  const compounds = (playerDossier && playerDossier.compounds) || [];
  const drugSuggestions = Array.from(new Set([
    ...playerCo.knownDrugs,
    ...compounds.map(c => c.name).filter(Boolean)
  ]));

  const submitMove = () => {
    if (!moveType) return;
    const headline = moveType.label + ": " + (fields.target_drug || fields.asset || "TBD");
    onSubmit({ type: moveType.id, headline, ...fields, _meta: { round: roundNumber, player: playerCo.name } });
    setMoveType(null);
    setFields({});
  };

  return (
    <div style={{ background: playerCo.color + "10", border: "2px solid " + playerCo.color, borderRadius: 12, padding: 20, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: playerCo.color }} />
        <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 15, color: playerCo.color }}>
          ROUND {roundNumber} · YOUR MOVE
        </div>
      </div>

      {!moveType ? (
        <>
          <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 12, letterSpacing: "0.05em" }}>SELECT MOVE TYPE</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
            {MOVE_TYPES.map(m => (
              <button key={m.id} onClick={() => setMoveType(m)} style={{
                background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, padding: 14,
                cursor: "pointer", fontFamily: "inherit", textAlign: "left", color: "#e6edf3",
              }}>
                <div style={{ fontSize: 18, marginBottom: 6 }}>{m.icon}</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 12, marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontSize: 10, color: "#8b949e", lineHeight: 1.4 }}>{m.desc}</div>
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <button onClick={() => { setMoveType(null); setFields({}); }} style={{
              background: "transparent", border: "1px solid #30363d", borderRadius: 6,
              padding: "4px 12px", color: "#8b949e", cursor: "pointer", fontFamily: "inherit", fontSize: 11,
            }}>← BACK</button>
            <span style={{ fontSize: 18 }}>{moveType.icon}</span>
            <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14 }}>{moveType.label}</div>
          </div>

          <div style={{ display: "grid", gap: 12 }}>
            {moveType.fields.map(f => (
              <FieldInput key={f} fieldId={f} value={fields[f] || ""}
                onChange={v => setFields(prev => ({ ...prev, [f]: v }))}
                drugSuggestions={drugSuggestions} trials={trials} />
            ))}
          </div>

          <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={submitMove} disabled={moveType.fields.some(f => !fields[f])}
              style={{
                background: playerCo.color, border: "none", borderRadius: 6,
                padding: "10px 20px", color: "#fff", fontFamily: "inherit", fontSize: 12,
                fontWeight: 600, cursor: "pointer", letterSpacing: "0.05em",
                opacity: moveType.fields.some(f => !fields[f]) ? 0.5 : 1,
              }}>
              EXECUTE MOVE → SIMULATE REACTIONS
            </button>
          </div>
        </>
      )}
    </div>
  );
}

const FIELD_LABELS = {
  target_drug: "Target Drug / Asset",
  discount_pct: "Discount %",
  geography: "Geography",
  timing: "Execution Timing",
  indication: "Indication",
  phase: "Phase",
  expansion: "Label Expansion Detail",
  evidence_source: "Supporting Evidence",
  trial_id: "Trial ID (NCT)",
  endpoint: "Primary Endpoint",
  asset: "Target Asset",
  deal_size: "Deal Size ($M)",
  new_formulation: "New Formulation",
  advantage: "Key Advantage",
  region: "Target Region",
  approach: "Entry Approach",
  from_segment: "From Segment",
  to_segment: "To Segment",
};

function FieldInput({ fieldId, value, onChange, drugSuggestions, trials }) {
  const label = FIELD_LABELS[fieldId] || fieldId;
  const labelEl = <label style={{ fontSize: 11, color: "#8b949e", marginBottom: 4, display: "block", letterSpacing: "0.05em" }}>{label}</label>;
  const inputStyle = { width: "100%", background: "#0d1117", border: "1px solid #30363d", borderRadius: 6, padding: "10px 12px", color: "#e6edf3", fontFamily: "inherit", fontSize: 12 };

  if (fieldId === "target_drug") {
    return (
      <div>{labelEl}
        <select value={value} onChange={e => onChange(e.target.value)} style={inputStyle}>
          <option value="">— select —</option>
          {drugSuggestions.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
    );
  }
  if (fieldId === "trial_id") {
    return (
      <div>{labelEl}
        <select value={value} onChange={e => onChange(e.target.value)} style={inputStyle}>
          <option value="">— select trial —</option>
          {trials.map(t => <option key={t.nct} value={t.nct}>{t.nct} · {(t.title || "").slice(0, 50)}</option>)}
        </select>
      </div>
    );
  }
  if (fieldId === "discount_pct") {
    return (
      <div>
        <label style={{ fontSize: 11, color: "#8b949e", marginBottom: 4, display: "block", letterSpacing: "0.05em" }}>{label}: {value || 0}%</label>
        <input type="range" min="0" max="60" value={value || 0} onChange={e => onChange(e.target.value)} style={{ width: "100%", accentColor: "#1f6feb" }} />
      </div>
    );
  }
  if (fieldId === "phase") {
    return (
      <div>{labelEl}
        <select value={value} onChange={e => onChange(e.target.value)} style={inputStyle}>
          <option value="">— select —</option>
          {["Phase 1", "Phase 2", "Phase 3", "Pivotal", "Filed"].map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
    );
  }
  if (fieldId === "timing") {
    return (
      <div>{labelEl}
        <select value={value} onChange={e => onChange(e.target.value)} style={inputStyle}>
          <option value="">— select —</option>
          {["Q2 2026", "Q3 2026", "Q4 2026", "H1 2027", "H2 2027", "2028+"].map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
    );
  }
  return (
    <div>{labelEl}
      <input type="text" value={value} onChange={e => onChange(e.target.value)} style={inputStyle} />
    </div>
  );
}

// ─── FLOW DIAGRAM ──────────────────────────────────────────────
function FlowDiagram({ round, companies }) {
  const playerColor = round.playerColor;
  const reactionMap = Object.fromEntries(REACTION_TYPES.map(r => [r.id, r]));

  return (
    <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 20, marginBottom: 16 }}>
      <div style={{ fontSize: 11, color: "#8b949e", letterSpacing: "0.1em", marginBottom: 16 }}>ROUND {round.roundNumber} · FLOW VIEW</div>

      <svg viewBox="0 0 900 400" style={{ width: "100%", display: "block", background: "#0d1117", borderRadius: 8 }}>
        <g>
          <rect x="20" y="140" width="240" height="120" rx="10" fill={playerColor + "20"} stroke={playerColor} strokeWidth="2" />
          <text x="40" y="170" fill={playerColor} style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 11, letterSpacing: "0.05em" }}>
            {round.playerCompany.toUpperCase()}
          </text>
          <text x="40" y="195" fill="#e6edf3" style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, fontWeight: 600 }}>
            {(round.playerMove.headline || "").slice(0, 30)}
          </text>
          <text x="40" y="215" fill="#8b949e" style={{ fontFamily: "'DM Mono', monospace", fontSize: 9 }}>
            {round.playerMove.timing || ""}
          </text>
          {round.playerMove.discount_pct ? (
            <text x="40" y="235" fill="#f0883e" style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, fontWeight: 600 }}>
              -{round.playerMove.discount_pct}% price
            </text>
          ) : null}
        </g>

        {round.reactions.map((rx, i) => {
          const co = companies.find(c => c.name === rx.company) || { color: "#8b949e" };
          const rstyle = reactionMap[rx.reaction_type] || { color: "#8b949e", label: rx.reaction_type || "n/a" };
          const yPos = 50 + i * 110;
          const cardX = 560;
          const lineEndY = yPos + 50;
          const path = "M 260 200 C 380 200, 440 " + lineEndY + ", 560 " + lineEndY;

          return (
            <g key={i}>
              <path d={path} fill="none" stroke={co.color} strokeWidth="2" opacity="0.5" />
              <rect x={cardX} y={yPos} width="320" height="100" rx="8" fill={co.color + "15"} stroke={co.color} strokeWidth="1.5" />
              <text x={cardX + 16} y={yPos + 22} fill={co.color} style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 11 }}>
                {rx.company.toUpperCase()}
              </text>
              <rect x={cardX + 200} y={yPos + 12} width="105" height="16" rx="8" fill={rstyle.color} opacity="0.25" />
              <text x={cardX + 252} y={yPos + 23} textAnchor="middle" fill={rstyle.color} style={{ fontFamily: "'DM Mono', monospace", fontSize: 8, fontWeight: 700 }}>
                {rstyle.label.toUpperCase()}
              </text>
              <text x={cardX + 16} y={yPos + 45} fill="#e6edf3" style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, fontWeight: 600 }}>
                {(rx.headline || "").slice(0, 38)}
              </text>
              <text x={cardX + 16} y={yPos + 62} fill="#8b949e" style={{ fontFamily: "'DM Mono', monospace", fontSize: 9 }}>
                {((rx.asset_leveraged && rx.asset_leveraged.name) || "").slice(0, 40)}
              </text>
              <text x={cardX + 16} y={yPos + 80} fill="#58a6ff" style={{ fontFamily: "'DM Mono', monospace", fontSize: 8 }}>
                {(rx.evidence_basis || []).slice(0, 2).join(" · ")}
              </text>
              <text x={cardX + 16} y={yPos + 95} fill="#8b949e" style={{ fontFamily: "'DM Mono', monospace", fontSize: 8 }}>
                Δ: {(rx.scores && rx.scores.market_share_delta) !== undefined ? rx.scores.market_share_delta + "%" : "—"} · T: {(rx.scores && rx.scores.time_to_execute_months) || "—"}mo · $: {(rx.scores && rx.scores.capex_required_musd) || "—"}M
              </text>
            </g>
          );
        })}
      </svg>

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", color: "#8b949e", fontSize: 11, padding: "8px 0" }}>SHOW DETAILED RATIONALES ▾</summary>
        <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
          {round.reactions.map((rx, i) => {
            const co = companies.find(c => c.name === rx.company) || { color: "#8b949e" };
            return (
              <div key={i} style={{ background: "#0d1117", borderLeft: "3px solid " + co.color, padding: 12, borderRadius: 4 }}>
                <div style={{ fontSize: 12, color: co.color, fontWeight: 700, marginBottom: 4 }}>{rx.company}</div>
                <div style={{ fontSize: 12, color: "#e6edf3", marginBottom: 6 }}>{rx.specific_action}</div>
                <div style={{ fontSize: 11, color: "#c9d1d9", lineHeight: 1.6, marginBottom: 6 }}>{rx.rationale}</div>
                {rx.ripple_target && (
                  <div style={{ fontSize: 10, color: "#f0883e", marginTop: 6, padding: "4px 8px", background: "#161b22", borderRadius: 4 }}>
                    ↻ Predicted ripple: {rx.ripple_target}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}

// ─── REACTION MATRIX ───────────────────────────────────────────
function ReactionMatrix({ round, companies }) {
  const reactionMap = Object.fromEntries(REACTION_TYPES.map(r => [r.id, r]));

  const scoreColor = (val, dimId) => {
    if (val === undefined || val === null) return "#30363d";
    if (dimId === "market_share_delta") {
      if (val > 3) return "#3fb950";
      if (val > 0) return "#3fb95080";
      if (val > -3) return "#f0883e80";
      return "#f85149";
    }
    if (dimId === "time_to_execute_months") return val < 12 ? "#3fb95080" : "#f0883e80";
    if (dimId === "capex_required_musd") return val < 500 ? "#3fb95080" : "#f0883e80";
    if (dimId === "regulatory_risk") return val < 5 ? "#3fb95080" : "#f0883e80";
    if (dimId === "payer_acceptance") return val > 5 ? "#3fb95080" : "#f0883e80";
    return "#8b949e";
  };

  return (
    <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 20, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 11, color: "#8b949e", letterSpacing: "0.1em" }}>ROUND {round.roundNumber} · MATRIX VIEW</div>
        <div style={{ marginLeft: "auto", fontSize: 11, color: round.playerColor, fontWeight: 600 }}>
          {round.playerCompany}: {round.playerMove.headline}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, fontSize: 11 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "#8b949e", letterSpacing: "0.05em", borderBottom: "1px solid #30363d" }}>COMPANY</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "#8b949e", letterSpacing: "0.05em", borderBottom: "1px solid #30363d" }}>REACTION</th>
              <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "#8b949e", letterSpacing: "0.05em", borderBottom: "1px solid #30363d" }}>ASSET</th>
              {REACTION_DIMENSIONS.map(dim => (
                <th key={dim.id} style={{ textAlign: "center", padding: "8px 8px", fontWeight: 600, color: "#8b949e", letterSpacing: "0.05em", borderBottom: "1px solid #30363d" }}>{dim.label}</th>
              ))}
              <th style={{ textAlign: "center", padding: "8px 8px", fontWeight: 600, color: "#8b949e", letterSpacing: "0.05em", borderBottom: "1px solid #30363d" }}>CONF</th>
            </tr>
          </thead>
          <tbody>
            {round.reactions.map((rx, i) => {
              const co = companies.find(c => c.name === rx.company) || { color: "#8b949e" };
              const rstyle = reactionMap[rx.reaction_type] || { color: "#8b949e", label: rx.reaction_type || "n/a" };
              return (
                <tr key={i} style={{ borderBottom: "1px solid #21262d" }}>
                  <td style={{ padding: "12px", verticalAlign: "top" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: co.color }} />
                      <span style={{ color: co.color, fontWeight: 700, fontFamily: "'Syne', sans-serif", fontSize: 12 }}>{rx.company}</span>
                    </div>
                  </td>
                  <td style={{ padding: "12px", verticalAlign: "top" }}>
                    <div style={{ display: "inline-block", padding: "3px 10px", background: rstyle.color + "25", color: rstyle.color, borderRadius: 10, fontSize: 10, fontWeight: 700, letterSpacing: "0.05em" }}>
                      {rstyle.label.toUpperCase()}
                    </div>
                    <div style={{ fontSize: 11, color: "#e6edf3", marginTop: 6, fontWeight: 500 }}>{rx.headline}</div>
                  </td>
                  <td style={{ padding: "12px", verticalAlign: "top" }}>
                    <div style={{ fontSize: 11, color: "#e6edf3", fontWeight: 500 }}>{(rx.asset_leveraged && rx.asset_leveraged.name) || "—"}</div>
                    <div style={{ fontSize: 9, color: "#58a6ff", fontFamily: "'DM Mono', monospace", marginTop: 3 }}>{(rx.asset_leveraged && rx.asset_leveraged.id) || ""}</div>
                  </td>
                  {REACTION_DIMENSIONS.map(dim => {
                    const val = rx.scores && rx.scores[dim.id];
                    const bg = scoreColor(val, dim.id);
                    const display = (val !== undefined && val !== null)
                      ? ((dim.id === "market_share_delta" && val > 0 ? "+" : "") + val)
                      : "—";
                    return (
                      <td key={dim.id} style={{ padding: "8px 4px", textAlign: "center", verticalAlign: "top" }}>
                        <div style={{ display: "inline-block", padding: "8px 10px", background: bg + "25", border: "1px solid " + bg, borderRadius: 6, minWidth: 50 }}>
                          <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, fontWeight: 700, color: "#e6edf3" }}>{display}</div>
                          <div style={{ fontSize: 8, color: "#8b949e", marginTop: 2 }}>{dim.unit}</div>
                        </div>
                      </td>
                    );
                  })}
                  <td style={{ padding: "12px", textAlign: "center", verticalAlign: "top" }}>
                    <div style={{ display: "inline-block", padding: "2px 8px", borderRadius: 8,
                      background: rx.confidence === "high" ? "#3fb95025" : rx.confidence === "medium" ? "#f0883e25" : "#f8514925",
                      color: rx.confidence === "high" ? "#3fb950" : rx.confidence === "medium" ? "#f0883e" : "#f85149",
                      fontSize: 9, fontWeight: 700, letterSpacing: "0.05em",
                    }}>{(rx.confidence || "low").toUpperCase()}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 16, padding: 12, background: "#0d1117", borderRadius: 6 }}>
        <div style={{ fontSize: 10, color: "#8b949e", marginBottom: 8, letterSpacing: "0.05em" }}>EVIDENCE GROUNDING</div>
        <div style={{ display: "grid", gap: 6 }}>
          {round.reactions.map((rx, i) => {
            const co = companies.find(c => c.name === rx.company) || { color: "#8b949e" };
            const ev = rx.evidence_basis || [];
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 11 }}>
                <span style={{ color: co.color, fontWeight: 600, minWidth: 100 }}>{rx.company}:</span>
                {ev.length === 0 ? (
                  <span style={{ color: "#484f58", fontSize: 10 }}>(no specific IDs)</span>
                ) : ev.map((e, ei) => (
                  <span key={ei} style={{
                    fontSize: 9, padding: "2px 8px", background: "#161b22",
                    border: "1px solid #30363d", borderRadius: 4, color: "#58a6ff",
                    fontFamily: "'DM Mono', monospace",
                  }}>{e}</span>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── BRIEFING VIEW ─────────────────────────────────────────────
function BriefingView({ companies, playerCo, rounds, briefing, briefingLoading, finalizeBriefing, dossierCount }) {
  const renderBriefing = (text) => {
    if (!text) return null;
    const names = companies.map(c => c.name);
    const escaped = names.map(escapeRegex).join("|");
    const pattern = new RegExp("(" + escaped + "|NCT\\d+|PMID:?\\s?\\d+|CHEMBL\\d+)", "gi");
    return text.split(pattern).map((part, i) => {
      const co = companies.find(c => c.name.toLowerCase() === part.toLowerCase());
      if (co) return <span key={i} style={{ color: co.color, fontWeight: 600 }}>{part}</span>;
      if (/^(NCT|PMID|CHEMBL)/i.test(part)) {
        return <span key={i} style={{ background: "#0d1117", color: "#58a6ff", padding: "1px 6px", borderRadius: 4, fontSize: 11, fontFamily: "'DM Mono', monospace" }}>{part}</span>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  const totalReactions = rounds.reduce((s, r) => s + r.reactions.length, 0);

  return (
    <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 22 }}>📋</span>
        <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16 }}>
          Executive Briefing — for {playerCo && playerCo.name}
        </div>
      </div>
      <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 20, lineHeight: 1.6 }}>
        Synthesized from {rounds.length} round{rounds.length !== 1 ? "s" : ""} ({totalReactions} reactions) + {dossierCount} dossiers.
      </div>
      {!briefing && !briefingLoading && rounds.length > 0 && (
        <button onClick={finalizeBriefing} style={{
          background: "#1f6feb", border: "none", borderRadius: 8, padding: "12px 24px",
          color: "#fff", cursor: "pointer", fontFamily: "inherit", fontSize: 12,
          fontWeight: 600, letterSpacing: "0.05em",
        }}>📋 GENERATE BRIEFING</button>
      )}
      {briefingLoading && <div className="pulse" style={{ color: "#8b949e", fontSize: 13 }}>Synthesizing...</div>}
      {briefing && <div style={{ fontSize: 14, lineHeight: 1.8, color: "#e6edf3", whiteSpace: "pre-wrap" }}>{renderBriefing(briefing)}</div>}
      {!briefing && !briefingLoading && rounds.length === 0 && (
        <div style={{ color: "#8b949e", fontSize: 13 }}>Play at least one round, then generate.</div>
      )}
    </div>
  );
}

// ─── GRAPH VIEW ────────────────────────────────────────────────
function GraphView({ query, entities, loading, results, hoveredEntity, setHoveredEntity, onJumpToSource }) {
  const W = 900, H = 600, cx = W / 2, cy = H / 2;
  const ENTITY_COLORS = { drug: "#27ae60", gene: "#9b59b6", condition: "#e74c3c", code: "#e67e22", provider: "#34495e", trial: "#8e44ad", organization: "#16a085" };

  const activeSources = useMemo(() => SOURCES.filter(s => Array.isArray(results[s.id]) && results[s.id].length > 0), [results]);

  const sourcePositions = useMemo(() => {
    const pos = {};
    const r = 180;
    activeSources.forEach((s, i) => {
      const angle = (i / activeSources.length) * Math.PI * 2 - Math.PI / 2;
      pos[s.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), angle };
    });
    return pos;
  }, [activeSources]);

  const entityPositions = useMemo(() => {
    const pos = {};
    entities.forEach((e, i) => {
      const angles = (e.provenance || []).map(p => sourcePositions[p.sourceId] && sourcePositions[p.sourceId].angle).filter(a => a !== undefined);
      if (angles.length === 0) return;
      const avgX = angles.reduce((a, b) => a + Math.cos(b), 0) / angles.length;
      const avgY = angles.reduce((a, b) => a + Math.sin(b), 0) / angles.length;
      const angle = Math.atan2(avgY, avgX);
      const r = 290 + (i % 3) * 18;
      pos[i] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), angle };
    });
    return pos;
  }, [entities, sourcePositions]);

  if (loading) return <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 60, textAlign: "center" }}>
    <div className="pulse" style={{ color: "#8b949e" }}>Extracting entities...</div></div>;

  if (entities.length === 0) return <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
    <div style={{ color: "#8b949e" }}>No entities yet.</div></div>;

  return (
    <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 24 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16 }}>Provenance Graph</div>
          <div style={{ fontSize: 11, color: "#8b949e", marginTop: 4 }}>{entities.length} entities · {activeSources.length} sources · hover to trace</div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {Object.entries(ENTITY_COLORS).map(([type, c]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#8b949e" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />{type}
            </div>
          ))}
        </div>
      </div>
      <div style={{ overflow: "auto", background: "#0d1117", borderRadius: 8 }}>
        <svg viewBox={"0 0 " + W + " " + H} style={{ width: "100%", display: "block", minWidth: 600 }}>
          <circle cx={cx} cy={cy} r={180} fill="none" stroke="#21262d" strokeDasharray="2 4" />
          <circle cx={cx} cy={cy} r={290} fill="none" stroke="#21262d" strokeDasharray="2 4" />
          {entities.map((e, ei) => {
            const ePos = entityPositions[ei];
            if (!ePos) return null;
            return (e.provenance || []).map((p, pi) => {
              const sPos = sourcePositions[p.sourceId];
              if (!sPos) return null;
              const highlighted = hoveredEntity === ei;
              const dimmed = hoveredEntity !== null && !highlighted;
              const src = SOURCES.find(s => s.id === p.sourceId) || { color: "#8b949e" };
              return <line key={ei + "-" + pi} x1={sPos.x} y1={sPos.y} x2={ePos.x} y2={ePos.y}
                stroke={highlighted ? src.color : "#30363d"} strokeWidth={highlighted ? 2 : 1}
                opacity={dimmed ? 0.15 : highlighted ? 0.9 : 0.5} />;
            });
          })}
          {activeSources.map(s => {
            const sPos = sourcePositions[s.id];
            return <line key={"c-" + s.id} x1={cx} y1={cy} x2={sPos.x} y2={sPos.y} stroke={s.color} strokeWidth={2} opacity={0.4} />;
          })}
          <g>
            <circle cx={cx} cy={cy} r={42} fill="#1f6feb" opacity={0.15} />
            <circle cx={cx} cy={cy} r={32} fill="#1f6feb" />
            <text x={cx} y={cy - 4} textAnchor="middle" fill="#fff" style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 10 }}>QUERY</text>
            <text x={cx} y={cy + 9} textAnchor="middle" fill="#fff" style={{ fontFamily: "'DM Mono', monospace", fontSize: 10 }}>
              {query.length > 14 ? query.slice(0, 13) + "…" : query}
            </text>
          </g>
          {activeSources.map(s => {
            const pos = sourcePositions[s.id];
            const count = (results[s.id] || []).length;
            return (
              <g key={s.id} style={{ cursor: "pointer" }} onClick={() => onJumpToSource(s.id)}>
                <circle cx={pos.x} cy={pos.y} r={26} fill={s.color} opacity={0.2} />
                <circle cx={pos.x} cy={pos.y} r={20} fill={s.color} />
                <text x={pos.x} y={pos.y + 4} textAnchor="middle" style={{ fontSize: 14 }}>{s.icon}</text>
                <text x={pos.x} y={pos.y + 38} textAnchor="middle" fill="#e6edf3" style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 10 }}>{s.label.toUpperCase()}</text>
                <text x={pos.x} y={pos.y + 50} textAnchor="middle" fill="#8b949e" style={{ fontFamily: "'DM Mono', monospace", fontSize: 9 }}>{count} results</text>
              </g>
            );
          })}
          {entities.map((e, ei) => {
            const pos = entityPositions[ei];
            if (!pos) return null;
            const color = ENTITY_COLORS[e.type] || "#8b949e";
            const isHovered = hoveredEntity === ei;
            const dimmed = hoveredEntity !== null && !isHovered;
            const labelOnRight = pos.x > cx;
            const label = e.name.length > 20 ? e.name.slice(0, 19) + "…" : e.name;
            return (
              <g key={ei} style={{ cursor: "pointer" }} opacity={dimmed ? 0.3 : 1}
                onMouseEnter={() => setHoveredEntity(ei)} onMouseLeave={() => setHoveredEntity(null)}
                onClick={() => { const first = e.provenance && e.provenance[0]; if (first) onJumpToSource(first.sourceId); }}>
                <circle cx={pos.x} cy={pos.y} r={isHovered ? 9 : 6} fill={color} stroke={isHovered ? "#fff" : "none"} strokeWidth={2} />
                <text x={pos.x + (labelOnRight ? 12 : -12)} y={pos.y + 3} textAnchor={labelOnRight ? "start" : "end"}
                  fill={isHovered ? "#fff" : "#c9d1d9"} style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, fontWeight: isHovered ? 600 : 400 }}>{label}</text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}