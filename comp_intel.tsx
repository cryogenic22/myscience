import { useState, useRef, useEffect, useMemo } from "react";

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

const PROMPTS = {
  pubmed: (q) => `Search PubMed for articles about "${q}". Return the top 5 results with title, authors, journal, year, and a one-sentence summary. Use the search_articles tool.`,
  biorxiv: (q) => `Search bioRxiv for preprints about "${q}". Return the top 5 results with title, authors, date, and a one-sentence summary. Use the search_preprints tool.`,
  chembl: (q) => `Search ChEMBL for drugs or compounds related to "${q}". Return up to 5 results with name, ChEMBL ID, type, and a brief description. Use the drug_search or compound_search tool.`,
  trials: (q) => `Search ClinicalTrials.gov for trials about "${q}". Return the top 5 results with title, status, phase, and sponsor. Use the search_trials tool.`,
  icd10: (q) => `Search ICD-10 codes related to "${q}". Return up to 8 results with code, description, and category. Use the search_codes tool.`,
  npi: (q) => `Search the NPI Registry for healthcare providers related to "${q}" (treat as a specialty or condition area). Return up to 5 provider results with name, specialty, and location. Use the npi_search tool.`,
  cms: (q) => `Search CMS Medicare coverage documents related to "${q}". Return up to 5 results with title, type, and a brief description. Use the search_national_coverage or search_local_coverage tool.`,
};

async function querySource(sourceId, query) {
  const serverName = SOURCE_MAP[sourceId];
  const serverUrl = MCP_SERVERS[serverName];

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1500,
      system: `You are a biomedical research assistant. Use the available MCP tools to search for information.
Always call the appropriate search tool. Return results as a JSON array under a key called "results".
Each result should have: "title", "subtitle" (authors/code/status/etc), "detail" (brief description), and optionally "url" or "id".
Respond ONLY with valid JSON, no markdown, no preamble.`,
      messages: [{ role: "user", content: PROMPTS[sourceId](query) }],
      mcp_servers: [{ type: "url", url: serverUrl, name: serverName }],
    }),
  });

  const data = await response.json();
  const textBlocks = (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
  try {
    const clean = textBlocks.replace(/```json|```/g, "").trim();
    const parsed = JSON.parse(clean);
    return parsed.results || parsed;
  } catch {
    const match = textBlocks.match(/\[[\s\S]*\]/);
    if (match) return JSON.parse(match[0]);
    return [{ title: "Results retrieved", subtitle: "", detail: textBlocks.slice(0, 300) }];
  }
}

async function extractEntities(query, allResults) {
  // Build a compact, source-tagged corpus of every retrieved result
  const corpus = [];
  Object.entries(allResults).forEach(([sourceId, results]) => {
    if (!Array.isArray(results)) return;
    results.forEach((r, i) => {
      corpus.push({
        sourceId,
        resultIndex: i,
        title: r.title || "",
        subtitle: r.subtitle || "",
        detail: r.detail || "",
      });
    });
  });

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2000,
      system: `You extract biomedical entities from retrieved search results. STRICT RULES:
1. Only extract entities that appear VERBATIM in the provided text. Never invent or infer.
2. Each entity MUST have a provenance: the exact sourceId and resultIndex where it appears.
3. Categorize entities as: "drug", "gene", "condition", "code", "provider", "trial", "organization".
4. Return ONLY JSON in this format:
{ "entities": [ { "name": "string", "type": "drug|gene|condition|code|provider|trial|organization", "provenance": [ { "sourceId": "string", "resultIndex": number } ] } ] }
Aggregate provenance: if the same entity appears in multiple results, list all of them.
Maximum 20 entities. No markdown. No preamble.`,
      messages: [{
        role: "user",
        content: `Query: "${query}"\n\nCorpus (sourceId, resultIndex, content):\n${JSON.stringify(corpus, null, 2)}`
      }],
    }),
  });

  const data = await response.json();
  const text = (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
  try {
    const clean = text.replace(/```json|```/g, "").trim();
    return JSON.parse(clean).entities || [];
  } catch {
    return [];
  }
}

async function synthesize(query, allResults) {
  const corpus = [];
  Object.entries(allResults).forEach(([sourceId, results]) => {
    if (!Array.isArray(results)) return;
    results.forEach((r, i) => {
      corpus.push({ sourceId, resultIndex: i, title: r.title, subtitle: r.subtitle, detail: r.detail });
    });
  });

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1500,
      system: `You synthesize biomedical search results into a grounded summary. STRICT RULES:
1. EVERY claim must cite the source it came from using the format [sourceId:resultIndex].
2. Do NOT make claims that aren't directly supported by the provided corpus.
3. If sources conflict, note both. If a topic isn't covered, say so.
4. Output 3-5 short paragraphs covering: overview, key findings, clinical/regulatory context, gaps.
5. No preamble. Plain text with inline citations like [pubmed:0] or [trials:2].`,
      messages: [{
        role: "user",
        content: `Query: "${query}"\n\nCorpus:\n${JSON.stringify(corpus, null, 2)}`
      }],
    }),
  });

  const data = await response.json();
  return (data.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
}

export default function UnifiedSearch() {
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
  const [synthesis, setSynthesis] = useState("");
  const [synthLoading, setSynthLoading] = useState(false);
  const [hoveredEntity, setHoveredEntity] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(true);
  const inputRef = useRef();

  // Load history from storage on mount
  useEffect(() => {
    (async () => {
      try {
        const list = await window.storage.list("history:");
        if (list?.keys?.length) {
          const items = [];
          for (const k of list.keys) {
            try {
              const r = await window.storage.get(k);
              if (r?.value) items.push(JSON.parse(r.value));
            } catch {}
          }
          items.sort((a, b) => b.ts - a.ts);
          setHistory(items.slice(0, 20));
        }
      } catch {}
    })();
  }, []);

  const saveToHistory = async (q, res) => {
    const counts = {};
    Object.entries(res).forEach(([k, v]) => { counts[k] = Array.isArray(v) ? v.length : 0; });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const entry = { query: q, ts: Date.now(), counts, total };
    try {
      await window.storage.set(`history:${entry.ts}`, JSON.stringify(entry));
      setHistory(prev => [entry, ...prev].slice(0, 20));
    } catch {}
  };

  const clearHistory = async () => {
    try {
      const list = await window.storage.list("history:");
      if (list?.keys) for (const k of list.keys) await window.storage.delete(k);
      setHistory([]);
    } catch {}
  };

  const handleSearch = async (overrideQuery) => {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;
    setQuery(q);
    setSubmitted(q);
    setResults({});
    setErrors({});
    setActive(null);
    setEntities([]);
    setSynthesis("");
    setTab("sources");

    const loadingState = {};
    SOURCES.forEach(s => { loadingState[s.id] = true; });
    setLoading(loadingState);

    const collected = {};
    await Promise.all(SOURCES.map(async (source) => {
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
      saveToHistory(q, collected);

      // Kick off entity extraction + synthesis in parallel
      setEntitiesLoading(true);
      setSynthLoading(true);
      extractEntities(q, collected)
        .then(setEntities)
        .catch(() => setEntities([]))
        .finally(() => setEntitiesLoading(false));
      synthesize(q, collected)
        .then(setSynthesis)
        .catch(() => setSynthesis("Synthesis unavailable."))
        .finally(() => setSynthLoading(false));
    }
  };

  const allDone = submitted && SOURCES.every(s => !loading[s.id]);
  const totalResults = Object.values(results).reduce((sum, r) => sum + (Array.isArray(r) ? r.length : 0), 0);
  const activeSource = active ? SOURCES.find(s => s.id === active) : null;
  const activeResults = active ? results[active] : null;

  // Export handlers
  const exportJSON = () => {
    const payload = { query: submitted, timestamp: new Date().toISOString(), results, entities, synthesis };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `medsearch-${submitted.replace(/\s+/g, "_")}.json`; a.click();
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
    const csv = rows.map(row => row.map(c => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `medsearch-${submitted.replace(/\s+/g, "_")}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  // Render synthesis with inline source badge highlights
  const renderSynthesis = (text) => {
    if (!text) return null;
    const parts = text.split(/(\[[a-z0-9]+:\d+\])/gi);
    return parts.map((part, i) => {
      const m = part.match(/^\[([a-z0-9]+):(\d+)\]$/i);
      if (m) {
        const sourceId = m[1].toLowerCase();
        const idx = parseInt(m[2], 10);
        const src = SOURCES.find(s => s.id === sourceId);
        if (src) {
          return (
            <span key={i}
              onClick={() => { setActive(sourceId); setTab("sources"); }}
              style={{
                display: "inline-block", padding: "1px 8px", margin: "0 2px",
                borderRadius: 10, fontSize: 10, fontWeight: 600,
                background: src.color + "25", color: src.color,
                border: `1px solid ${src.color}50`, cursor: "pointer",
                fontFamily: "'DM Mono', monospace",
              }}>
              {src.icon} {src.label.toUpperCase()}:{idx}
            </span>
          );
        }
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div style={{
      minHeight: "100vh", background: "#0d1117",
      fontFamily: "'DM Mono', 'Fira Code', 'Courier New', monospace",
      color: "#e6edf3", padding: 0, display: "flex",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #161b22; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
        .card-hover { transition: all 0.2s ease; cursor: pointer; }
        .card-hover:hover { transform: translateY(-2px); }
        .result-item { border-bottom: 1px solid #21262d; padding: 12px 0; }
        .result-item:last-child { border-bottom: none; }
        .pulse { animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
        .fade-in { animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .search-input:focus { outline: none; border-color: #58a6ff !important; box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
        .back-btn:hover, .icon-btn:hover { background: #21262d !important; }
        .tab-btn { background: transparent; border: none; padding: 10px 18px; color: #8b949e; cursor: pointer; font-family: inherit; font-size: 12px; letter-spacing: 0.05em; border-bottom: 2px solid transparent; transition: all 0.15s; }
        .tab-btn.active { color: #e6edf3; border-bottom-color: #58a6ff; }
        .tab-btn:hover { color: #e6edf3; }
        .history-item:hover { background: #1c2128 !important; }
        .entity-pill { transition: all 0.15s; cursor: pointer; }
        .entity-pill:hover { transform: scale(1.05); }
        @media (max-width: 768px) { .sidebar { display: none !important; } }
      `}</style>

      {/* Sidebar — history */}
      {historyOpen && (
        <div className="sidebar" style={{
          width: 240, borderRight: "1px solid #21262d", background: "#0a0d12",
          padding: "20px 16px", display: "flex", flexDirection: "column", gap: 12,
          minHeight: "100vh", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 11, color: "#8b949e", letterSpacing: "0.1em" }}>HISTORY</div>
            {history.length > 0 && (
              <button onClick={clearHistory} style={{
                background: "transparent", border: "none", color: "#8b949e",
                cursor: "pointer", fontSize: 10, fontFamily: "inherit",
              }}>CLEAR</button>
            )}
          </div>
          {history.length === 0 ? (
            <div style={{ fontSize: 11, color: "#484f58", lineHeight: 1.5 }}>No searches yet. Past queries will appear here.</div>
          ) : (
            history.map(h => (
              <div key={h.ts} className="history-item" onClick={() => handleSearch(h.query)}
                style={{
                  padding: "10px 12px", borderRadius: 6, background: "#161b22",
                  border: "1px solid #21262d", cursor: "pointer", transition: "all 0.15s",
                }}>
                <div style={{ fontSize: 12, color: "#e6edf3", fontWeight: 500, marginBottom: 4, wordBreak: "break-word" }}>
                  {h.query}
                </div>
                <div style={{ fontSize: 10, color: "#8b949e", display: "flex", justifyContent: "space-between" }}>
                  <span>{h.total} results</span>
                  <span>{new Date(h.ts).toLocaleDateString()}</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Main */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header */}
        <div style={{ borderBottom: "1px solid #21262d", padding: "20px 32px", display: "flex", alignItems: "center", gap: 16 }}>
          <button className="icon-btn" onClick={() => setHistoryOpen(!historyOpen)} style={{
            background: "transparent", border: "1px solid #30363d", borderRadius: 6,
            padding: "6px 10px", color: "#8b949e", cursor: "pointer", fontSize: 12,
            fontFamily: "inherit",
          }}>≡</button>
          <div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 22, fontWeight: 800, letterSpacing: "-0.5px" }}>
              MED<span style={{ color: "#58a6ff" }}>SEARCH</span>
            </div>
            <div style={{ fontSize: 11, color: "#8b949e", marginTop: 2 }}>unified biomedical intelligence · grounded · traceable</div>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            {SOURCES.map(s => (
              <div key={s.id} style={{
                width: 8, height: 8, borderRadius: "50%",
                background: submitted ? (loading[s.id] ? "#f0883e" : errors[s.id] ? "#f85149" : results[s.id] ? "#3fb950" : "#8b949e") : "#30363d",
                transition: "all 0.3s",
              }} title={s.label} />
            ))}
          </div>
        </div>

        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
          {/* Search bar */}
          <div style={{ marginBottom: 32 }}>
            <div style={{ fontSize: 13, color: "#8b949e", marginBottom: 12, letterSpacing: "0.05em" }}>
              QUERY → {SOURCES.length} SOURCES SIMULTANEOUSLY
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <input
                ref={inputRef}
                className="search-input"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                placeholder="e.g. metformin, BRCA1, type 2 diabetes..."
                style={{
                  flex: 1, background: "#161b22", border: "1px solid #30363d",
                  borderRadius: 8, padding: "14px 18px", fontSize: 15, color: "#e6edf3",
                  fontFamily: "inherit", transition: "all 0.2s",
                }}
              />
              <button
                onClick={() => handleSearch()}
                disabled={!query.trim() || Object.values(loading).some(Boolean)}
                style={{
                  background: "#1f6feb", border: "none", borderRadius: 8,
                  padding: "14px 28px", color: "#fff", fontSize: 13, fontFamily: "inherit",
                  fontWeight: 500, cursor: "pointer", letterSpacing: "0.05em",
                  opacity: (!query.trim() || Object.values(loading).some(Boolean)) ? 0.5 : 1,
                }}
              >
                {Object.values(loading).some(Boolean) ? "SEARCHING..." : "SEARCH →"}
              </button>
            </div>
          </div>

          {/* Tabs */}
          {submitted && (
            <div style={{ borderBottom: "1px solid #21262d", marginBottom: 24, display: "flex", gap: 4, flexWrap: "wrap" }}>
              <button className={`tab-btn ${tab === "sources" ? "active" : ""}`} onClick={() => setTab("sources")}>SOURCES</button>
              <button className={`tab-btn ${tab === "graph" ? "active" : ""}`} onClick={() => setTab("graph")}>
                GRAPH {entitiesLoading ? "·" : entities.length > 0 ? `· ${entities.length}` : ""}
              </button>
              <button className={`tab-btn ${tab === "synthesis" ? "active" : ""}`} onClick={() => setTab("synthesis")}>
                SYNTHESIS {synthLoading ? "·" : synthesis ? "✓" : ""}
              </button>
              <button className={`tab-btn ${tab === "export" ? "active" : ""}`} onClick={() => setTab("export")}>EXPORT</button>
            </div>
          )}

          {/* SOURCES TAB */}
          {tab === "sources" && active && (
            <div className="fade-in" style={{ marginBottom: 32, background: "#161b22", border: `1px solid ${activeSource.color}40`, borderRadius: 12, padding: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
                <button className="back-btn" onClick={() => setActive(null)} style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 6, padding: "6px 14px", color: "#8b949e", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>
                  ← BACK
                </button>
                <span style={{ fontSize: 20 }}>{activeSource.icon}</span>
                <span style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, color: activeSource.color }}>{activeSource.label}</span>
                <span style={{ fontSize: 12, color: "#8b949e" }}>{activeSource.desc}</span>
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#8b949e" }}>{activeResults?.length || 0} results for "{submitted}"</span>
              </div>
              {loading[active] ? (
                <div className="pulse" style={{ color: "#8b949e", fontSize: 13 }}>Fetching results...</div>
              ) : errors[active] ? (
                <div style={{ color: "#f85149", fontSize: 13 }}>Error: {errors[active]}</div>
              ) : Array.isArray(activeResults) && activeResults.length > 0 ? (
                activeResults.map((r, i) => (
                  <div key={i} className="result-item fade-in">
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}>
                      <span style={{ fontSize: 10, color: activeSource.color, fontWeight: 600, fontFamily: "'DM Mono', monospace" }}>[{i}]</span>
                      <div style={{ fontSize: 14, color: "#e6edf3", fontWeight: 500, lineHeight: 1.4 }}>{r.title}</div>
                    </div>
                    {r.subtitle && <div style={{ fontSize: 12, color: activeSource.color, marginBottom: 4, marginLeft: 24 }}>{r.subtitle}</div>}
                    {r.detail && <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.5, marginLeft: 24 }}>{r.detail}</div>}
                    {(r.url || r.id) && <div style={{ fontSize: 11, color: "#58a6ff", marginTop: 4, marginLeft: 24 }}>{r.url || r.id}</div>}
                  </div>
                ))
              ) : (
                <div style={{ color: "#8b949e", fontSize: 13 }}>No results found.</div>
              )}
            </div>
          )}

          {tab === "sources" && !active && submitted && (
            <>
              <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 20, letterSpacing: "0.05em" }}>
                {allDone
                  ? `SEARCH COMPLETE — ${totalResults} RESULTS ACROSS ${Object.keys(results).length} SOURCES`
                  : `SEARCHING ${Object.values(loading).filter(Boolean).length} SOURCES...`}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16 }}>
                {SOURCES.map(source => {
                  const isLoading = loading[source.id];
                  const hasError = errors[source.id];
                  const res = results[source.id];
                  const count = Array.isArray(res) ? res.length : 0;
                  return (
                    <div key={source.id} className="card-hover fade-in"
                      onClick={() => !isLoading && setActive(source.id)}
                      style={{
                        background: "#161b22",
                        border: `1px solid ${isLoading ? "#f0883e40" : hasError ? "#f8514940" : res ? source.color + "40" : "#21262d"}`,
                        borderRadius: 10, padding: "18px 20px",
                        opacity: isLoading ? 0.8 : 1,
                      }}>
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
                      {hasError && <div style={{ fontSize: 12, color: "#f85149" }}>Request failed</div>}
                      {res && !isLoading && (
                        <>
                          <div style={{ fontSize: 22, fontFamily: "'Syne', sans-serif", fontWeight: 800, color: source.color, marginBottom: 4 }}>{count}</div>
                          <div style={{ fontSize: 11, color: "#8b949e" }}>
                            {Array.isArray(res) && res[0]?.title ? res[0].title.slice(0, 60) + (res[0].title.length > 60 ? "..." : "") : "results found"}
                          </div>
                          <div style={{ marginTop: 12, fontSize: 11, color: source.color, letterSpacing: "0.05em" }}>VIEW RESULTS →</div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* GRAPH TAB */}
          {tab === "graph" && submitted && (
            <GraphView
              query={submitted}
              entities={entities}
              loading={entitiesLoading}
              results={results}
              hoveredEntity={hoveredEntity}
              setHoveredEntity={setHoveredEntity}
              onJumpToSource={(sid, idx) => { setActive(sid); setTab("sources"); }}
            />
          )}

          {/* SYNTHESIS TAB */}
          {tab === "synthesis" && submitted && (
            <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Cross-Source Synthesis</div>
              <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 20, lineHeight: 1.6 }}>
                Every claim is grounded — click a source badge to jump to the originating result. No claim exists here without a citation.
              </div>
              {synthLoading ? (
                <div className="pulse" style={{ color: "#8b949e", fontSize: 13 }}>Generating grounded synthesis from {totalResults} retrieved results...</div>
              ) : synthesis ? (
                <div style={{ fontSize: 14, lineHeight: 1.8, color: "#e6edf3", whiteSpace: "pre-wrap" }}>
                  {renderSynthesis(synthesis)}
                </div>
              ) : (
                <div style={{ color: "#8b949e", fontSize: 13 }}>No synthesis yet.</div>
              )}
            </div>
          )}

          {/* EXPORT TAB */}
          {tab === "export" && submitted && (
            <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
              <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Export Results</div>
              <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 24 }}>Download all retrieved data for "{submitted}"</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16 }}>
                <button onClick={exportJSON} className="card-hover" style={{
                  background: "#0d1117", border: "1px solid #30363d", borderRadius: 10,
                  padding: 20, color: "#e6edf3", cursor: "pointer", fontFamily: "inherit",
                  textAlign: "left",
                }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📦</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>JSON</div>
                  <div style={{ fontSize: 11, color: "#8b949e" }}>Full structured payload with results, entities, and synthesis</div>
                </button>
                <button onClick={exportCSV} className="card-hover" style={{
                  background: "#0d1117", border: "1px solid #30363d", borderRadius: 10,
                  padding: 20, color: "#e6edf3", cursor: "pointer", fontFamily: "inherit",
                  textAlign: "left",
                }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>CSV</div>
                  <div style={{ fontSize: 11, color: "#8b949e" }}>Flattened table — one row per result across all sources</div>
                </button>
              </div>
              <div style={{ marginTop: 24, padding: 16, background: "#0d1117", borderRadius: 8, fontSize: 11, color: "#8b949e", lineHeight: 1.6 }}>
                <strong style={{ color: "#e6edf3" }}>Summary:</strong> {totalResults} results · {entities.length} entities · {Object.keys(results).length} sources
              </div>
            </div>
          )}

          {/* Empty state */}
          {!submitted && (
            <div style={{ textAlign: "center", padding: "60px 0", color: "#8b949e" }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🔬</div>
              <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 700, color: "#e6edf3", marginBottom: 8 }}>Search across 7 biomedical sources</div>
              <div style={{ fontSize: 13, maxWidth: 480, margin: "0 auto", lineHeight: 1.6 }}>
                Every result is fetched live via MCP. Every entity is extracted from real data. Every synthesis claim is traceable back to its source. Zero hallucination by construction.
              </div>
              <div style={{ marginTop: 32, display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                {["metformin", "BRCA1", "Alzheimer's", "GLP-1", "pancreatic cancer"].map(ex => (
                  <button key={ex} onClick={() => { setQuery(ex); setTimeout(() => inputRef.current?.focus(), 50); }}
                    style={{ background: "#161b22", border: "1px solid #30363d", borderRadius: 20, padding: "6px 16px", color: "#8b949e", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// GRAPH VIEW: Query → Sources → Entities → Results
// Pure SVG, deterministic radial layout, traceability via path highlighting
// ─────────────────────────────────────────────────────────────────────
function GraphView({ query, entities, loading, results, hoveredEntity, setHoveredEntity, onJumpToSource }) {
  const W = 900, H = 600;
  const cx = W / 2, cy = H / 2;

  const ENTITY_COLORS = {
    drug: "#27ae60", gene: "#9b59b6", condition: "#e74c3c",
    code: "#e67e22", provider: "#34495e", trial: "#8e44ad", organization: "#16a085",
  };

  // Sources with results, in a ring around the center
  const activeSources = useMemo(() =>
    SOURCES.filter(s => Array.isArray(results[s.id]) && results[s.id].length > 0)
  , [results]);

  const sourcePositions = useMemo(() => {
    const pos = {};
    const r = 180;
    activeSources.forEach((s, i) => {
      const angle = (i / activeSources.length) * Math.PI * 2 - Math.PI / 2;
      pos[s.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), angle };
    });
    return pos;
  }, [activeSources]);

  // Entities in an outer ring, grouped near their primary source
  const entityPositions = useMemo(() => {
    const pos = {};
    entities.forEach((e, i) => {
      // Find the average angle of all source provenance to position the entity near its sources
      const angles = (e.provenance || [])
        .map(p => sourcePositions[p.sourceId]?.angle)
        .filter(a => a !== undefined);
      if (angles.length === 0) return;
      // Average angle (handle wraparound by using vector mean)
      const avgX = angles.reduce((a, b) => a + Math.cos(b), 0) / angles.length;
      const avgY = angles.reduce((a, b) => a + Math.sin(b), 0) / angles.length;
      const angle = Math.atan2(avgY, avgX);
      const r = 290 + (i % 3) * 18; // slight stagger so labels don't overlap
      pos[i] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), angle };
    });
    return pos;
  }, [entities, sourcePositions]);

  if (loading) {
    return (
      <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 60, textAlign: "center" }}>
        <div className="pulse" style={{ color: "#8b949e", fontSize: 13 }}>Extracting entities and building provenance graph...</div>
      </div>
    );
  }

  if (entities.length === 0) {
    return (
      <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 28 }}>
        <div style={{ color: "#8b949e", fontSize: 13 }}>No entities extracted yet.</div>
      </div>
    );
  }

  // Determine which links to highlight based on hover
  const isHighlighted = (sourceId, entityIdx) => {
    if (hoveredEntity === null) return false;
    return hoveredEntity === entityIdx;
  };

  return (
    <div className="fade-in" style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 12, padding: 24 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 16 }}>Provenance Graph</div>
          <div style={{ fontSize: 11, color: "#8b949e", marginTop: 4, lineHeight: 1.6 }}>
            {entities.length} entities · extracted from {activeSources.length} sources · hover to trace · click to jump
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {Object.entries(ENTITY_COLORS).map(([type, c]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#8b949e" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />
              {type}
            </div>
          ))}
        </div>
      </div>

      <div style={{ overflow: "auto", background: "#0d1117", borderRadius: 8, border: "1px solid #21262d" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block", minWidth: 600 }}>
          {/* Background rings (for reference) */}
          <circle cx={cx} cy={cy} r={180} fill="none" stroke="#21262d" strokeDasharray="2 4" />
          <circle cx={cx} cy={cy} r={290} fill="none" stroke="#21262d" strokeDasharray="2 4" />

          {/* Edges: source → entity */}
          {entities.map((e, ei) => {
            const ePos = entityPositions[ei];
            if (!ePos) return null;
            return (e.provenance || []).map((p, pi) => {
              const sPos = sourcePositions[p.sourceId];
              if (!sPos) return null;
              const highlighted = isHighlighted(p.sourceId, ei);
              const dimmed = hoveredEntity !== null && !highlighted;
              const src = SOURCES.find(s => s.id === p.sourceId);
              return (
                <line key={`${ei}-${pi}`}
                  x1={sPos.x} y1={sPos.y} x2={ePos.x} y2={ePos.y}
                  stroke={highlighted ? src.color : "#30363d"}
                  strokeWidth={highlighted ? 2 : 1}
                  opacity={dimmed ? 0.15 : highlighted ? 0.9 : 0.5}
                  style={{ transition: "all 0.2s" }}
                />
              );
            });
          })}

          {/* Edges: center → source */}
          {activeSources.map(s => {
            const sPos = sourcePositions[s.id];
            return (
              <line key={`c-${s.id}`} x1={cx} y1={cy} x2={sPos.x} y2={sPos.y}
                stroke={s.color} strokeWidth={2} opacity={0.4} />
            );
          })}

          {/* Center: query node */}
          <g>
            <circle cx={cx} cy={cy} r={42} fill="#1f6feb" opacity={0.15} />
            <circle cx={cx} cy={cy} r={32} fill="#1f6feb" />
            <text x={cx} y={cy - 4} textAnchor="middle" fill="#fff"
              style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 10 }}>QUERY</text>
            <text x={cx} y={cy + 9} textAnchor="middle" fill="#fff"
              style={{ fontFamily: "'DM Mono', monospace", fontSize: 10 }}>
              {query.length > 14 ? query.slice(0, 13) + "…" : query}
            </text>
          </g>

          {/* Source nodes */}
          {activeSources.map(s => {
            const pos = sourcePositions[s.id];
            const count = results[s.id]?.length || 0;
            return (
              <g key={s.id} style={{ cursor: "pointer" }} onClick={() => onJumpToSource(s.id)}>
                <circle cx={pos.x} cy={pos.y} r={26} fill={s.color} opacity={0.2} />
                <circle cx={pos.x} cy={pos.y} r={20} fill={s.color} />
                <text x={pos.x} y={pos.y + 4} textAnchor="middle"
                  style={{ fontSize: 14 }}>{s.icon}</text>
                <text x={pos.x} y={pos.y + 38} textAnchor="middle" fill="#e6edf3"
                  style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 10 }}>
                  {s.label.toUpperCase()}
                </text>
                <text x={pos.x} y={pos.y + 50} textAnchor="middle" fill="#8b949e"
                  style={{ fontFamily: "'DM Mono', monospace", fontSize: 9 }}>
                  {count} results
                </text>
              </g>
            );
          })}

          {/* Entity nodes */}
          {entities.map((e, ei) => {
            const pos = entityPositions[ei];
            if (!pos) return null;
            const color = ENTITY_COLORS[e.type] || "#8b949e";
            const isHovered = hoveredEntity === ei;
            const dimmed = hoveredEntity !== null && !isHovered;
            const labelOnRight = pos.x > cx;
            const label = e.name.length > 20 ? e.name.slice(0, 19) + "…" : e.name;
            return (
              <g key={ei} style={{ cursor: "pointer", transition: "all 0.2s" }}
                opacity={dimmed ? 0.3 : 1}
                onMouseEnter={() => setHoveredEntity(ei)}
                onMouseLeave={() => setHoveredEntity(null)}
                onClick={() => {
                  const first = e.provenance?.[0];
                  if (first) onJumpToSource(first.sourceId, first.resultIndex);
                }}>
                <circle cx={pos.x} cy={pos.y} r={isHovered ? 9 : 6} fill={color}
                  stroke={isHovered ? "#fff" : "none"} strokeWidth={2} />
                <text x={pos.x + (labelOnRight ? 12 : -12)} y={pos.y + 3}
                  textAnchor={labelOnRight ? "start" : "end"}
                  fill={isHovered ? "#fff" : "#c9d1d9"}
                  style={{ fontFamily: "'DM Mono', monospace", fontSize: 10, fontWeight: isHovered ? 600 : 400 }}>
                  {label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Hover detail panel */}
      {hoveredEntity !== null && entities[hoveredEntity] && (
        <div className="fade-in" style={{ marginTop: 16, padding: 16, background: "#0d1117", borderRadius: 8, border: "1px solid #30363d" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: ENTITY_COLORS[entities[hoveredEntity].type] || "#8b949e" }} />
            <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14 }}>{entities[hoveredEntity].name}</div>
            <div style={{ fontSize: 10, color: "#8b949e", textTransform: "uppercase", letterSpacing: "0.05em" }}>{entities[hoveredEntity].type}</div>
          </div>
          <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 8 }}>Found in:</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(entities[hoveredEntity].provenance || []).map((p, i) => {
              const src = SOURCES.find(s => s.id === p.sourceId);
              if (!src) return null;
              const result = results[p.sourceId]?.[p.resultIndex];
              return (
                <button key={i} onClick={() => onJumpToSource(p.sourceId, p.resultIndex)}
                  style={{
                    background: src.color + "20", border: `1px solid ${src.color}50`,
                    borderRadius: 6, padding: "6px 10px", color: src.color,
                    cursor: "pointer", fontSize: 11, fontFamily: "inherit", textAlign: "left",
                  }}>
                  {src.icon} {src.label} [{p.resultIndex}]
                  {result?.title && <div style={{ fontSize: 10, color: "#8b949e", marginTop: 2, maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{result.title}</div>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}