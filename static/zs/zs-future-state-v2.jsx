import { useState, useMemo, useEffect, useRef } from "react";
import {
  ComposedChart, Area, Line, LineChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, PieChart, Pie, Cell,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";

/* ============================================================
   ZS FUTURE STATE · v2 (red-teamed)
   Framework · Risk-adjusted growth-bridge · Offering generator · Moats · Red team
   Adds: win-probability, competitive compression, cash vs recognised, margin J-curve,
         Monte-Carlo band + P(hit target), stress presets.
   Figures are illustrative — recalibrate with ZS internal data.
   ============================================================ */

const TOKENS = `
  :root{
    --paper:#F7F6F3; --surface:#FFFFFF; --surface-2:#FBFAF7;
    --ink:#16181C; --ink-soft:#5A5F66; --ink-faint:#9AA0A6;
    --line:#E5E2DB; --line-strong:#D4D0C6;
    --accent:#E8541E; --accent-deep:#C23F0E; --accent-soft:#FBE9E1;
    --core:#3A3F47; --recurring:#0E7C7B; --outcome:#E8541E; --project:#9AA0A6;
    --risk:#B23A48; --good:#0E7C7B; --cash:#1F6FB2;
    --s1:#E8541E; --s2:#0E7C7B; --s3:#3B4CB8; --s4:#C8881C; --s5:#6D4AAE; --s6:#C2456B;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    --sans:"Helvetica Neue",Arial,system-ui,sans-serif;
  }
  *{box-sizing:border-box}
  .fs-root{background:var(--paper);color:var(--ink);font-family:var(--sans);min-height:100%;-webkit-font-smoothing:antialiased;line-height:1.45;}
  .fs-num{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-0.01em;}
  .fs-eyebrow{font-family:var(--mono);text-transform:uppercase;letter-spacing:0.18em;font-size:10px;color:var(--ink-faint);font-weight:600;}
  .fs-h1{font-size:clamp(22px,3.4vw,34px);font-weight:800;letter-spacing:-0.025em;line-height:1.05;}
  .fs-h2{font-size:18px;font-weight:750;letter-spacing:-0.02em;}
  .fs-h3{font-size:13px;font-weight:700;letter-spacing:-0.01em;}
  .fs-wrap{max-width:1120px;margin:0 auto;padding:0 20px;}
  .fs-card{background:var(--surface);border:1px solid var(--line);border-radius:14px;}
  .fs-rule{height:1px;background:var(--line);border:0;}
  .fs-tab{font-family:var(--mono);font-size:11px;letter-spacing:0.07em;text-transform:uppercase;font-weight:600;padding:9px 12px;border-radius:999px;border:1px solid transparent;color:var(--ink-soft);cursor:pointer;background:transparent;transition:all .15s ease;white-space:nowrap;}
  .fs-tab:hover{color:var(--ink);}
  .fs-tab[data-on="1"]{background:var(--ink);color:#fff;}
  .fs-btn{font-family:var(--sans);font-size:13px;font-weight:650;padding:9px 15px;border-radius:9px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;transition:all .15s;}
  .fs-btn:hover{background:#000;}
  .fs-btn[data-variant="ghost"]{background:transparent;color:var(--ink);}
  .fs-btn[data-variant="ghost"]:hover{background:var(--surface-2);}
  .fs-btn[data-variant="accent"]{background:var(--accent);border-color:var(--accent);}
  .fs-btn[data-variant="accent"]:hover{background:var(--accent-deep);border-color:var(--accent-deep);}
  .fs-btn[data-variant="risk"]{background:transparent;color:var(--risk);border-color:var(--risk);}
  .fs-btn[data-variant="risk"]:hover{background:#FBEAEC;}
  .fs-btn:disabled{opacity:.45;cursor:not-allowed;}
  .fs-chip{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding:3px 7px;border-radius:6px;background:var(--surface-2);border:1px solid var(--line);color:var(--ink-soft);}
  input[type=range]{-webkit-appearance:none;appearance:none;height:3px;background:var(--line-strong);border-radius:3px;outline:none;width:100%;}
  input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;height:16px;width:16px;border-radius:50%;background:var(--ink);cursor:pointer;border:2px solid var(--surface);box-shadow:0 1px 3px rgba(0,0,0,.2);}
  input[type=range]::-moz-range-thumb{height:14px;width:14px;border-radius:50%;background:var(--ink);cursor:pointer;border:2px solid var(--surface);}
  select,input[type=text]{font-family:var(--sans);font-size:13px;padding:8px 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--surface);color:var(--ink);width:100%;}
  select:focus,input:focus{outline:2px solid var(--accent-soft);border-color:var(--accent);}
  .fs-fade{animation:fsFade .4s ease both;}
  @keyframes fsFade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  @media (prefers-reduced-motion:reduce){.fs-fade{animation:none}}
  .fs-quad{border:1px solid var(--line);border-radius:12px;padding:14px;cursor:pointer;transition:all .15s;background:var(--surface);}
  .fs-quad:hover{border-color:var(--line-strong);}
  .fs-quad[data-target="1"]{border-color:var(--accent);background:linear-gradient(180deg,var(--accent-soft),var(--surface));}
`;

/* ---------- domain model ---------- */
const POOLS = {
  ai:        { label:"Pharma AI / gen-AI spend", traj:"~$4B (2025) → ~$25.7B (2030)", weight:1.0 },
  rnd:       { label:"R&D / development / regulatory", traj:"~$180B pool · 30–40% of AI value", weight:1.0 },
  commercial:{ label:"Commercial transformation", traj:"25–35% of AI value", weight:0.85 },
  opmodel:   { label:"Operating-model / GCC build", traj:"clients insourcing the run", weight:0.8 },
  mna:       { label:"M&A / launch / portfolio", traj:"$170–400B patent cliff", weight:0.75 },
  governance:{ label:"Governance / trust / verification", traj:"new pool · FDA credibility", weight:0.7 },
};
const MODELS = {
  hybrid:    { label:"Hybrid: base + outcome layer", unit:"recurring fee + value bonus", quality:"recurring",
               note:"The default. Predictable floor for procurement, upside on outcomes; best net revenue retention." },
  perunit:   { label:"Per-unit digital labour", unit:"per artifact / decision rendered", quality:"outcome",
               note:"Bill the work done — per submission, per ePI, per decision. Fits discrete, high-value artifacts." },
  gainshare: { label:"Gain-share / outcome", unit:"share of measured lift", quality:"outcome",
               note:"Only where attribution is clean (launch trajectory, access pull-through). Needs the metering layer." },
  bot:       { label:"Build-Operate-Transfer (+operate)", unit:"build fee + operate retainer", quality:"project",
               note:"GCC-driven. Fight to keep the operate tail — the transfer is where the annuity leaks away." },
  subusage:  { label:"Subscription + usage", unit:"platform seat + consumption", quality:"recurring",
               note:"ZAIDYN-as-substrate. Own the run, not the licence — the run is where the durable margin sits." },
  assurance: { label:"Assurance-as-a-service", unit:"per certification + subscription", quality:"recurring",
               note:"Paid for verification and credibility. Unverified AI is now a P&L and legal matter." },
};
const VALUE_STREAMS = ["Launch","Market access","Medical affairs","Marketing-mix","Field / engagement",
  "Clinical development","Regulatory authoring","Patient services","Manufacturing / supply"];
const RTW = { high:{ label:"High", mult:1.0, attain:80 }, med:{ label:"Medium", mult:0.6, attain:62 }, low:{ label:"Low (white space)", mult:0.38, attain:45 } };

// canonical portfolio — note `attain` = probability the line reaches its target size (red-team addition)
const LIBRARY = [
  { id:"decisionops", name:"DecisionOps managed services", pool:"commercial", model:"hybrid",
    size:0.78, start:2, attain:62, color:"var(--s1)", buyer:"CCO · CDIO",
    moat:"Highest — governed decision systems run as a service",
    rationale:"World-④ product. The Decision Flywheel made into a recurring, outcome-priced business." },
  { id:"devreg", name:"Development & Regulatory AI", pool:"rnd", model:"perunit",
    size:0.58, start:2, attain:48, color:"var(--s2)", buyer:"CMO · Head of Reg/Dev",
    moat:"Governed authoring & regulatory credibility",
    rationale:"Biggest white space and biggest value pool — but lowest right-to-win. The reSCape / DocAce lineage; most M&A goes here." },
  { id:"cognitive", name:"Cognitive-enterprise build-operate-transfer", pool:"opmodel", model:"bot",
    size:0.45, start:1, attain:78, color:"var(--s3)", buyer:"CDIO · COO",
    moat:"Medium — operating model & reference architecture",
    rationale:"Front-loaded bridge revenue that funds the transition. Convert transfer into operate." },
  { id:"platform", name:"Platform & data substrate (ZAIDYN)", pool:"ai", model:"subusage",
    size:0.35, start:1, attain:66, color:"var(--s4)", buyer:"CDIO",
    moat:"Medium — orchestration kept proprietary",
    rationale:"New recurring revenue; the hedge. Keep orchestration & metering yours, not a platform feature." },
  { id:"trust", name:"Trust, governance & verification", pool:"governance", model:"assurance",
    size:0.25, start:3, attain:55, color:"var(--s5)", buyer:"Quality · Reg · Chief AI Officer",
    moat:"High — option value on GxP credibility",
    rationale:"New pool created by the FDA credibility framework and outcome accountability." },
  { id:"cliff", name:"Cliff & launch advisory (transformed)", pool:"mna", model:"gainshare",
    size:0.25, start:1, attain:72, color:"var(--s6)", buyer:"CCO · Corporate development",
    moat:"Medium-high — launch excellence on outcomes",
    rationale:"Rides the largest near-term demand event. Episodic but high-value." },
];

const QUALITY_LABELS = { recurring:"Recurring", outcome:"Outcome", project:"Project", core:"Transformed core" };
const QUALITY_COLORS = { recurring:"var(--recurring)", outcome:"var(--outcome)", project:"var(--project)", core:"var(--core)" };

/* ---------- moats & agent economics ---------- */
const MOAT_DIMS = {
  ground:     { label:"Decision ground-truth", short:"Ground-truth", durability:"Contested",
    pov:"The labelled outcomes of decisions you’ve run. It only compounds if you can aggregate across clients — and pharma confidentiality may forbid exactly that. Treat as a per-client asset until cross-client aggregation is contractually real." },
  compliance: { label:"Compliance & provenance", short:"Compliance", durability:"Strongest",
    pov:"Tokenised data, clean rooms, GxP audit trails, FDA-credibility alignment. The most durable moat — but IQVIA holds deep regulatory relationships too, so it’s a contest you must keep winning, not a given." },
  switching:  { label:"Embedded switching cost", short:"Switching", durability:"Strong",
    pov:"When you run the governed system in the flow of work, ripping it out is costly — roughly 75% of total cost of ownership sits in the run." },
  trust:      { label:"Trust / assurance", short:"Trust", durability:"Medium-strong",
    pov:"The standing to be handed the high-stakes decision and believed when you say you proved it. Assurance makes trust a line item." },
  convenience:{ label:"Convenience / in-flow", short:"Convenience", durability:"Secondary",
    pov:"Aids retention, but a platform that owns the surface can out-convenience you. Never rest the defence here." },
};
const OFFERING_MOATS = {
  decisionops:{ ground:3, compliance:2, switching:3, trust:2, convenience:2 },
  devreg:     { ground:3, compliance:3, switching:2, trust:3, convenience:1 },
  cognitive:  { ground:1, compliance:2, switching:2, trust:1, convenience:2 },
  platform:   { ground:2, compliance:2, switching:2, trust:1, convenience:3 },
  trust:      { ground:2, compliance:3, switching:1, trust:3, convenience:1 },
  cliff:      { ground:1, compliance:1, switching:1, trust:2, convenience:1 },
};
function deriveMoats(pool, model){
  const base = {
    rnd:{ground:3,compliance:3,switching:2,trust:3,convenience:1}, commercial:{ground:3,compliance:2,switching:3,trust:2,convenience:2},
    ai:{ground:2,compliance:2,switching:2,trust:1,convenience:3}, opmodel:{ground:1,compliance:2,switching:2,trust:1,convenience:2},
    governance:{ground:2,compliance:3,switching:1,trust:3,convenience:1}, mna:{ground:1,compliance:1,switching:1,trust:2,convenience:1},
  };
  const v = { ...(base[pool]||base.commercial) };
  if(model==="bot") v.switching=Math.max(0,v.switching-1);
  if(model==="assurance"){ v.trust=3; v.compliance=3; }
  if(model==="subusage"){ v.convenience=3; v.trust=Math.max(0,v.trust-1); }
  if(model==="hybrid") v.switching=Math.min(3,v.switching+1);
  return v;
}
// Prefer a card's own edited moat scores; fall back to the canonical
// OFFERING_MOATS table, then to derivation from pool+model.
function getMoats(line){ return line.moats || OFFERING_MOATS[line.id] || deriveMoats(line.pool, line.model); }
const AGENT_LAYERS = [
  { layer:"Frontier intelligence", stance:"Rent", note:"Commodity input — rent from the labs. Risk: the labs move down into delivery and can see your usage." },
  { layer:"Orchestration · governance · ground-truth", stance:"Own", note:"The moat layer. Own it — but guard it, because it’s exactly what the labs will try to build." },
  { layer:"Governed agents · assurance · decision systems", stance:"Licence", note:"Productise and licence as IP — the route to software-like margin and platform scale." },
];

/* ---------- math ---------- */
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function legacyAt(base,erosionPct,shapeP,t,H){ if(t<=0)return base; const x=clamp(t/H,0,1); const g=1-Math.pow(1-x,shapeP); return base*(1-(erosionPct/100)*g); }
function rampFrac(start,H,t){ if(t<start)return 0; const span=Math.max(H-start,0.0001); const p=clamp((t-start)/span,0,1); return p*p*(3-2*p); }
function gauss(m,sd){ let u=0,v=0; while(!u)u=Math.random(); while(!v)v=Math.random(); return m+sd*Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }
// margin by quality and age (years since start) — the J-curve
function lineMargin(q,age){
  const m={ outcome:{s:-0.12,g:0.085,cap:0.34}, recurring:{s:0.03,g:0.075,cap:0.36}, project:{s:0.18,g:0.012,cap:0.23}, core:{s:0.27,g:0,cap:0.29} }[q]||{s:0.15,g:0,cap:0.25};
  return Math.min(m.cap, m.s + m.g*Math.max(0,age));
}

/* ---------- persistence (file-backed JSON via /zs/api, no DB) ----------
   The deck is buildless; these are plain fetch() calls. credentials:'include'
   re-attaches the HTTP Basic header the page is already gated by. If the API is
   unreachable (e.g. the .jsx opened as a static file), callers fall back to the
   baked-in LIBRARY so the deck still works offline. */
const CARDS_API = "/zs/api/cards";
// Normalise a server/library card into the shape the simulator consumes.
function normCard(c){ return { ...c, attain: c.attain ?? 60, enabled: c.enabled !== false }; }
// The baked-in fallback set (server seeds from the identical LIBRARY).
function libraryCards(){ return LIBRARY.map(l=>normCard({ ...l, moats: OFFERING_MOATS[l.id] })); }
async function apiListCards(){
  const r = await fetch(CARDS_API, { credentials:"include", cache:"no-cache" });
  if(!r.ok) throw new Error("GET cards -> HTTP "+r.status);
  const j = await r.json();
  return (j.cards||[]).map(normCard);
}
async function apiWrite(method, path, body){
  const r = await fetch(path, { method, credentials:"include", headers:{"Content-Type":"application/json"},
    body: body===undefined?undefined:JSON.stringify(body) });
  if(!r.ok){ let d=""; try{ d=JSON.stringify((await r.json()).detail); }catch(e){} throw new Error(method+" "+path+" -> HTTP "+r.status+(d?` · ${d}`:"")); }
  return r.status===204?null:r.json();
}
// strip the client-only `enabled` flag before persisting
function cardForApi(c){ const { enabled, ...rest } = c; return rest; }

/* ---------- two more editable, file-persisted card families ----------
   `constructs` (how we charge) and `bets` (where we place big chips) ride the
   identical /zs/api persistence as the capability cards. Each has a baked-in
   fallback set (a 1:1 mirror of the server seed) so the deck still works when
   opened as a static file with the API unreachable. */
const CONSTRUCTS_API = "/zs/api/constructs";
const BETS_API = "/zs/api/bets";
const CONSTRUCT_QUALITIES = ["recurring","outcome","project"];
const BET_HORIZONS = ["near","mid","moonshot"];
const BET_POSTURES = ["build","partner","consume"];
const HORIZON_LABELS = { near:"Near", mid:"Mid", moonshot:"Moonshot" };
const POSTURE_LABELS = { build:"Build", partner:"Partner", consume:"Consume" };
const POSTURE_COLORS = { build:"var(--accent-deep)", partner:"var(--cash)", consume:"var(--ink-faint)" };

const DEFAULT_CONSTRUCTS = [
  { id:"floor-per-hit", name:"Floor + per-hit", meter:"A discrete, pre-agreed outcome event ('a hit')",
    value_story:"A fixed base retainer covers ZS's delivery-cost floor and de-risks procurement; a success fee fires per realized outcome event.",
    quality:"outcome", buyer:"CFO / procurement + the business owner",
    zs_risk:"Defining the 'hit' tight enough to be attributable yet loose enough to fire often.",
    fit:"Needs a clean, discrete, attributable event.",
    examples:"First-cycle FDA acceptance · formulary add · launch month-6 inside a trajectory band · a field action that clears a pre-agreed threshold" },
  { id:"decision-latency-sla", name:"Decision-latency SLA", meter:"Time from data-capture → decision, against a guaranteed SLA",
    value_story:"You don't sell the model — you sell the weeks of spend reallocated earlier. 'Allocation-ready answer in N days or you don't pay the premium.' A platform structurally can't sell this; ZS can because ZS runs it.",
    quality:"recurring", buyer:"Brand / commercial lead",
    zs_risk:"Owning the data plumbing end-to-end to actually hit the SLA.",
    fit:"A slow, repeated decision cycle you can compress and own.",
    examples:"Marketing-mix cycle 3 months → 4 weeks · brand-plan reallocation · trial-enrollment decision compression" },
  { id:"gain-share", name:"Gain-share / outcome", meter:"A share of measured lift",
    value_story:"Only where attribution is clean. Build holdout/geo-experiment design into delivery so you become the agreed scorekeeper — itself a moat.",
    quality:"outcome", buyer:"Commercial / market access",
    zs_risk:"Confounding — the drug's success isn't all your intervention.",
    fit:"Clean attribution plus a metering/measurement layer.",
    examples:"Access pull-through (formulary → script lift) · launch vs. analog benchmark · incremental Rx from next-best-action" },
  { id:"cost-to-serve-takeout", name:"Cost-to-serve takeout", meter:"% below the client's insourced/GCC cost + an operate retainer",
    value_story:"Price against the fully-loaded cost they avoid, with governance they can't staff. Makes the operate tail the product (fights BOT transfer leakage).",
    quality:"project", buyer:"COO / CDIO",
    zs_risk:"Margin compression if the takeout % is too aggressive.",
    fit:"Where the client's alternative is a GCC / insourcing.",
    examples:"MLR review throughput · medical-information ops · analytics run" },
  { id:"assurance-per-cert", name:"Assurance / per-cert", meter:"Per validated decision / certified model / audit-ready artifact",
    value_story:"Sell credibility as a line item. Near-zero marginal cost on the Nth certification through a governed harness.",
    quality:"recurring", buyer:"Quality · Regulatory · Chief AI Officer",
    zs_risk:"Liability if a certified output is later challenged.",
    fit:"Regulated outputs under the FDA credibility framework.",
    examples:"Per-ePI · per-submission · per-model-validation" },
  { id:"outcome-underwriting", name:"Outcome underwriting (frontier)", meter:"A guaranteed floor + shared upside on a decision outcome",
    value_story:"The purest 'outcome operator' — you take a position. Requires balance-sheet capacity + actuarial data (the flywheel).",
    quality:"outcome", buyer:"CCO / corporate development",
    zs_risk:"Can't run on a billable-hour P&L; gated on the flywheel-ownership question.",
    fit:"Year 3-5, only once cross-client ground-truth is contractually real.",
    examples:"Launch outcome guarantee · access-win guarantee" },
];
const DEFAULT_BETS = [
  { id:"simulation-aas", name:"Decision Simulation-as-a-Service",
    thesis:"Run the decision before you make it — launch/payer/allocation/portfolio sims. ZS is already building the simulator (the v2 instrument), and it compounds the flywheel.",
    unit_moat:"Per-simulation / subscription; moat = calibration data (your decision ground-truth makes your sims more right than a generic one).",
    kill_criterion:"If the sims aren't demonstrably better-calibrated than generic or the client's own → it's Monte-Carlo theater.",
    ceiling:"$1B", horizon:"near", posture:"build", native:true },
  { id:"digital-twin", name:"Digital Twin",
    thesis:"A living, governed twin of an asset / market / patient population / trial that you keep in sync and run scenarios against — pure 'translation' craft.",
    unit_moat:"Subscription per twin + usage; the twin is the substrate, simulation is the verb on it.",
    kill_criterion:"RWD / data rights — IQVIA owns much of the underlying data; partner or contest.",
    ceiling:"$1B", horizon:"mid", posture:"build", native:true },
  { id:"pharma-slms", name:"Pharma SLMs",
    thesis:"Don't build frontier (rent it). Own small, governable, domain-tuned models for narrow regulated tasks (ePI, CRL, MLR), tuned on your decision corpus. Instantiates rent-frontier / own-the-orchestration.",
    unit_moat:"Embedded in the service-as-software units or licensed on-prem; moat = the training corpus + the eval harness that proves them.",
    kill_criterion:"Frontier models get cheap + governable enough to erase the edge — keep it a thin layer.",
    ceiling:"$0.5–1B", horizon:"mid", posture:"build", native:true },
  { id:"the-harness", name:"The Harness (governance standard)",
    thesis:"The eval/governance/orchestration layer is the moat the strategy says to own. Make it the de-facto standard FDA-credibility runs through → a tollbooth on every governed pharma AI decision, including competitors'. The sleeper bet.",
    unit_moat:"Subscription + per-certification; standards-ownership is winner-take-most.",
    kill_criterion:"A hyperscaler or IQVIA sets the standard first, or FDA blesses someone else's framework.",
    ceiling:"$1B+", horizon:"moonshot", posture:"build", native:true },
  { id:"quantum", name:"Quantum",
    thesis:"Almost certainly NOT ZS to build — ZS would be the application/translation layer on someone else's quantum (rent the intelligence again).",
    unit_moat:"A research partnership + a small option stake, not a revenue line.",
    kill_criterion:"Don't let a buzzword become a budget line — the right posture is an option, not a line.",
    ceiling:"Speculative", horizon:"moonshot", posture:"partner", native:false },
  { id:"hardware-edge", name:"Hardware / edge",
    thesis:"Weakest fit — capital-heavy, low-margin, far from the craft. The only angle: a governed decision appliance inside a pharma firewall for sensitive SLM inference — and partner for the metal.",
    unit_moat:"Consume, don't build.",
    kill_criterion:"Deprioritize as a revenue bet entirely.",
    ceiling:"Low", horizon:"moonshot", posture:"consume", native:false },
];
// Fetch a family's set; throws on a non-OK response so the caller can fall back.
async function apiListFamily(api){
  const r = await fetch(api, { credentials:"include", cache:"no-cache" });
  if(!r.ok) throw new Error("GET "+api+" -> HTTP "+r.status);
  const j = await r.json();
  return j.cards || [];
}

/* ---------- small components ---------- */
function Stat({ label, value, unit, tone, sub }){
  const color = tone==="good"?"var(--good)":tone==="risk"?"var(--risk)":tone==="accent"?"var(--accent)":"var(--ink)";
  return (<div>
    <div className="fs-eyebrow" style={{marginBottom:5}}>{label}</div>
    <div className="fs-num" style={{fontSize:24,fontWeight:700,color,lineHeight:1}}>{value}<span style={{fontSize:12,color:"var(--ink-faint)",marginLeft:3}}>{unit}</span></div>
    {sub && <div style={{fontSize:10.5,color:"var(--ink-faint)",marginTop:3}}>{sub}</div>}
  </div>);
}
function Slider({ label, value, min, max, step, onChange, fmt, tone }){
  return (<div style={{marginBottom:13}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",marginBottom:6}}>
      <span style={{fontSize:12,color:"var(--ink-soft)",fontWeight:600}}>{label}</span>
      <span className="fs-num" style={{fontSize:13,fontWeight:700,color:tone==="risk"?"var(--risk)":"var(--ink)"}}>{fmt?fmt(value):value}</span>
    </div>
    <input type="range" min={min} max={max} step={step} value={value} onChange={e=>onChange(parseFloat(e.target.value))}/>
  </div>);
}

/* ============================================================ */
export default function ZSFutureState(){
  const [tab,setTab]=useState("frame");
  const [base,setBase]=useState(2.4);
  const [erosion,setErosion]=useState(50);
  const [shape,setShape]=useState(2);
  const [target,setTarget]=useState(3.6);
  const [H,setH]=useState(5);
  // Capability cards are the source of truth — seeded from the baked-in LIBRARY
  // and replaced by the persisted set from /zs/api/cards on mount (see effect).
  const [lines,setLines]=useState(libraryCards());
  const [cardsStatus,setCardsStatus]=useState("loading"); // loading | live | offline
  // The two extra editable, file-persisted families (constructs + bets). Seeded
  // from the baked-in fallback, replaced by the persisted set on mount.
  const [constructs,setConstructs]=useState(DEFAULT_CONSTRUCTS);
  const [constructsStatus,setConstructsStatus]=useState("loading");
  const [bets,setBets]=useState(DEFAULT_BETS);
  const [betsStatus,setBetsStatus]=useState("loading");
  // red-team risk parameters
  const [compression,setCompression]=useState(8);   // annual competitive price compression on NEW lines, % at year H
  const [haircut,setHaircut]=useState(10);           // outcome revenue dispute/clawback %
  const [cashLag,setCashLag]=useState(1);            // collection lag (yrs) on outcome revenue
  const [execDiscount,setExecDiscount]=useState(0);  // global execution discount on all win-probabilities, %
  const [saved,setSaved]=useState(false);
  const loaded=useRef(false);

  // Load the persisted capability cards (file-backed via /zs/api/cards). On
  // failure, keep the baked-in LIBRARY so the deck still works opened locally.
  const refreshCards=async()=>{ try{ const c=await apiListCards(); setLines(c); setCardsStatus("live"); return c; }
    catch(e){ console.warn("ZS cards API unreachable — using baked-in LIBRARY:",e.message); setCardsStatus("offline"); return null; } };
  const refreshConstructs=async()=>{ try{ const c=await apiListFamily(CONSTRUCTS_API); setConstructs(c); setConstructsStatus("live"); return c; }
    catch(e){ console.warn("ZS constructs API unreachable — using baked-in defaults:",e.message); setConstructsStatus("offline"); return null; } };
  const refreshBets=async()=>{ try{ const c=await apiListFamily(BETS_API); setBets(c); setBetsStatus("live"); return c; }
    catch(e){ console.warn("ZS bets API unreachable — using baked-in defaults:",e.message); setBetsStatus("offline"); return null; } };
  useEffect(()=>{ refreshCards(); refreshConstructs(); refreshBets(); },[]);
  // Legacy scenario restore (the slider inputs only — cards are now server-side,
  // so this no longer overwrites the card set).
  useEffect(()=>{(async()=>{ try{ if(window.storage){ const r=await window.storage.get("zs-fs-v2:scenario");
    if(r&&r.value){ const s=JSON.parse(r.value); setBase(s.base);setErosion(s.erosion);setShape(s.shape);setTarget(s.target);setH(s.H);
      setCompression(s.compression??8);setHaircut(s.haircut??10);setCashLag(s.cashLag??1);setExecDiscount(s.execDiscount??0);} } }catch(e){} loaded.current=true; })();},[]);
  async function saveScenario(){ try{ if(window.storage){ await window.storage.set("zs-fs-v2:scenario",JSON.stringify({base,erosion,shape,target,H,compression,haircut,cashLag,execDiscount})); setSaved(true); setTimeout(()=>setSaved(false),1800);} }catch(e){} }
  function resetScenario(){ setBase(2.4);setErosion(50);setShape(2);setTarget(3.6);setH(5);setCompression(8);setHaircut(10);setCashLag(1);setExecDiscount(0); }
  function applyPreset(p){ setErosion(p.erosion);setCompression(p.compression);setHaircut(p.haircut);setCashLag(p.cashLag);setExecDiscount(p.exec); }

  const model = useMemo(()=>{
    const years=Array.from({length:H+1},(_,i)=>i);
    const enabled=lines.filter(l=>l.enabled);
    const eff = l => clamp((l.attain??60)*(1-execDiscount/100),3,100)/100;     // effective win-probability
    const comp = t => 1-(compression/100)*(t/H);                               // competitive compression on new lines
    const data = years.map(t=>{
      const row={ year:t, legacy:+legacyAt(base,erosion,shape,t,H).toFixed(4) };
      let exp=row.legacy, cash=row.legacy, gross=row.legacy;
      enabled.forEach(l=>{
        const q=MODELS[l.model].quality, a=eff(l);
        const rev=+(l.size*rampFrac(l.start,H,t)*a*comp(t)).toFixed(4);
        row[l.id]=rev; exp+=rev; gross+=l.size*rampFrac(l.start,H,t);
        const lag=q==="outcome"?cashLag:0, hc=q==="outcome"?(1-haircut/100):1;
        cash+= l.size*rampFrac(l.start,H,Math.max(0,t-lag))*a*comp(t)*hc;
      });
      row.total=+exp.toFixed(4); row.cash=+cash.toFixed(4); row.gross=+gross.toFixed(4);
      return row;
    });
    const last=data[data.length-1];
    const landing=last.total, grossLanding=last.gross, cashLanding=last.cash;
    const gap=+(target-landing).toFixed(3);
    const survivor=last.legacy;
    // troughs (years 1..H)
    let tr={y:0,v:base}, ctr={y:0,v:base};
    data.slice(1).forEach(r=>{ if(r.total<tr.v)tr={y:r.year,v:r.total}; if(r.cash<ctr.v)ctr={y:r.year,v:r.cash}; });
    // quality mix (risk-adjusted, year H)
    const mix={ core:survivor, recurring:0, outcome:0, project:0 };
    enabled.forEach(l=>{ mix[MODELS[l.model].quality]+=last[l.id]; });
    const newTotal=mix.recurring+mix.outcome+mix.project;
    const highQshare=landing>0?Math.round(((mix.recurring+mix.outcome)/landing)*100):0;
    // margin J-curve
    const marginData=years.map(t=>{
      let num=0,den=0; const lg=legacyAt(base,erosion,shape,t,H); den+=lg; num+=lg*lineMargin("core",t);
      enabled.forEach(l=>{ const q=MODELS[l.model].quality,a=eff(l); const rev=l.size*rampFrac(l.start,H,t)*a*comp(t); den+=rev; num+=rev*lineMargin(q,t-l.start); });
      return { year:t, margin: den>0?+(num/den*100).toFixed(1):0 };
    });
    const marginH=marginData[marginData.length-1].margin;
    const marginTrough=Math.min(...marginData.slice(1).map(d=>d.margin));
    // moat profile (risk-weighted)
    const dims=Object.keys(MOAT_DIMS); const prof={}; dims.forEach(d=>prof[d]=0); let wsum=0;
    enabled.forEach(l=>{ const mv=getMoats(l); const w=last[l.id]||0; wsum+=w; dims.forEach(d=>prof[d]+=(mv[d]||0)*w); });
    dims.forEach(d=>prof[d]=wsum>0?+(prof[d]/wsum).toFixed(2):0);
    const defens=wsum>0?Math.round((dims.reduce((s,d)=>s+prof[d],0)/dims.length)/3*100):0;
    // Monte-Carlo on year-H landing
    const N=500, samples=[];
    for(let i=0;i<N;i++){
      const er=clamp(gauss(erosion,8),0,92);
      let tot=legacyAt(base,er,shape,H,H);
      enabled.forEach(l=>{ const a=clamp(gauss((l.attain??60)*(1-execDiscount/100),13),3,100)/100; const cp=1-clamp(gauss(compression,6),0,65)/100; tot+=l.size*a*cp; });
      samples.push(tot);
    }
    samples.sort((a,b)=>a-b);
    const pq=q=>samples[clamp(Math.floor(q*(N-1)),0,N-1)];
    const p10=+pq(0.1).toFixed(2),p50=+pq(0.5).toFixed(2),p90=+pq(0.9).toFixed(2);
    const pHit=Math.round(samples.filter(s=>s>=target).length/N*100);
    return { data, years, enabled, landing, grossLanding, cashLanding, gap, survivor, tr, ctr, mix, newTotal, highQshare,
      marginData, marginH, marginTrough, prof, defens, p10, p50, p90, pHit };
  },[base,erosion,shape,target,H,lines,compression,haircut,cashLag,execDiscount]);

  const fmtB=v=>`$${v.toFixed(2)}B`;
  const risk={compression,setCompression,haircut,setHaircut,cashLag,setCashLag,execDiscount,setExecDiscount};

  return (
    <div className="fs-root">
      <style>{TOKENS}</style>
      <div style={{borderBottom:"1px solid var(--line)",background:"var(--surface)",position:"sticky",top:0,zIndex:20}}>
        <div className="fs-wrap" style={{paddingTop:16,paddingBottom:14}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16,flexWrap:"wrap"}}>
            <div>
              <div className="fs-eyebrow">ZS · future-state instrument · v2 (red-teamed)</div>
              <div className="fs-h1" style={{marginTop:6,maxWidth:560}}>Rebuilding two-thirds of the firm</div>
              <div style={{color:"var(--ink-soft)",fontSize:13,marginTop:6,maxWidth:560}}>
                Risk-adjusted, not aspirational. Win-probability, competitive compression and cash timing are now in the model.
              </div>
            </div>
            <div style={{display:"flex",gap:20,paddingTop:4,flexWrap:"wrap"}}>
              <Stat label="Expected landing" value={model.landing.toFixed(2)} unit="B" tone="accent" sub={`gross ${fmtB(model.grossLanding)}`}/>
              <Stat label={model.gap<=0?"Headroom":"Gap to target"} value={Math.abs(model.gap).toFixed(2)} unit="B" tone={model.gap<=0?"good":"risk"}/>
              <Stat label="P(hit target)" value={model.pHit} unit="%" tone={model.pHit>=60?"good":model.pHit>=35?"accent":"risk"} sub={`P10–P90 ${model.p10}–${model.p90}`}/>
              <Stat label="Defensibility" value={model.defens} unit="/100" tone={model.defens>=66?"good":"accent"}/>
            </div>
          </div>
          <div style={{display:"flex",gap:5,marginTop:14,flexWrap:"wrap"}}>
            {[["frame","Framework"],["build","Capabilities"],["constructs","Constructs"],["bets","Bets"],["sim","Risk-adjusted bridge"],["gen","Offering generator"],["moats","Moats & agent economics"],["red","Red team"],["model","Commercial models"]].map(([k,l])=>(
              <button key={k} className="fs-tab" data-on={tab===k?"1":"0"} onClick={()=>setTab(k)}>{l}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="fs-wrap" style={{paddingTop:24,paddingBottom:60}}>
        {tab==="frame" && <FrameView/>}
        {tab==="build" && <BuildView {...{lines,setLines,cardsStatus,refreshCards}}/>}
        {tab==="constructs" && <ConstructsView {...{constructs,setConstructs,constructsStatus,refreshConstructs}}/>}
        {tab==="bets" && <BetsView {...{bets,setBets,betsStatus,refreshBets}}/>}
        {tab==="sim" && <SimView {...{base,setBase,erosion,setErosion,shape,setShape,target,setTarget,H,setH,lines,setLines,model,fmtB,saveScenario,resetScenario,saved,risk}}/>}
        {tab==="gen" && <GenView onAdd={async(l)=>{
            // Persist the generated offering, then refetch; fall back to a
            // local add if the API is unreachable so the demo still flows.
            try{ await apiWrite("POST",CARDS_API,cardForApi(l)); await refreshCards(); }
            catch(e){ console.warn("ZS add via API failed — local-only:",e.message); setLines(p=>[...p,normCard(l)]); }
            setTab("sim"); }}/>}
        {tab==="moats" && <MoatView model={model}/>}
        {tab==="red" && <RedTeamView model={model} applyPreset={applyPreset} fmtB={fmtB} risk={risk}/>}
        {tab==="model" && <ModelView/>}
      </div>

      <div style={{borderTop:"1px solid var(--line)",background:"var(--surface)"}}>
        <div className="fs-wrap" style={{paddingTop:14,paddingBottom:14,display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
          <span style={{fontSize:11,color:"var(--ink-faint)"}}>Illustrative. Win-probabilities, compression and margin curves are judgement calls — calibrate with ZS data.</span>
          <span className="fs-eyebrow">decision instrument · not a forecast</span>
        </div>
      </div>
    </div>
  );
}

/* ---------- Framework ---------- */
function FrameView(){
  const [q,setQ]=useState(4);
  const worlds={
    1:{ t:"① Commodity squeeze", d:"Platforms supply the agents; GCCs run them. ZS pushed to change-management scraps. Refuse this by abandoning the execution base deliberately, not defending it." },
    2:{ t:"② Implementation partner", d:"ZS is the elite pharma implementation arm for Veeva / Salesforce / IQVIA. Decent, lower-margin, partner-dependent. Participate as a hedge — don’t let it define the brand." },
    3:{ t:"③ Capability builder", d:"Sell the operating model, reference architecture and governance; build-operate-transfer. High value, but each engagement trains its replacement. Hedge into it; keep the operate." },
    4:{ t:"④ Cognitive system integrator", d:"Own and run governed decision systems as a managed service, paid on outcomes, on a ZAIDYN substrate. Highest moat — but contested by IQVIA. Force this world, and keep winning the contest." },
  };
  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div className="fs-eyebrow">The wedge</div>
      <div className="fs-h2" style={{marginTop:7}}>Governed decision systems in regulated environments, sold and priced as outcomes.</div>
      <p style={{color:"var(--ink-soft)",fontSize:13,marginTop:8,maxWidth:760}}>Lead as the integrator, monetise as the operator, use the platform play only as substrate. The wedge is narrower and more contested than it looks — IQVIA holds data scale and regulatory depth — so treat it as a contest to keep winning, not a position you own.</p>
    </div>
    <div className="fs-eyebrow" style={{marginBottom:10}}>Where to play — two uncertainties, four worlds</div>
    <div style={{display:"grid",gridTemplateColumns:"160px 1fr 1fr",gap:10,marginBottom:18}}>
      <div></div>
      <div className="fs-eyebrow" style={{textAlign:"center",alignSelf:"center"}}>Clients insource</div>
      <div className="fs-eyebrow" style={{textAlign:"center",alignSelf:"center"}}>Clients outsource</div>
      <div className="fs-eyebrow" style={{alignSelf:"center"}}>Platform captures value</div>
      <Quad w={worlds[1]} on={q===1} go={()=>setQ(1)}/><Quad w={worlds[2]} on={q===2} go={()=>setQ(2)}/>
      <div className="fs-eyebrow" style={{alignSelf:"center"}}>Orchestration captures value</div>
      <Quad w={worlds[3]} on={q===3} go={()=>setQ(3)}/><Quad w={worlds[4]} on={q===4} go={()=>setQ(4)} target/>
    </div>
    <div className="fs-card" style={{padding:16,marginBottom:22}}><div className="fs-h3">{worlds[q].t}</div><p style={{fontSize:13,color:"var(--ink-soft)",marginTop:6}}>{worlds[q].d}</p></div>
    <div className="fs-eyebrow" style={{marginBottom:10}}>Three horizons</div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:10,marginBottom:22}}>
      {[["H1 · Protect & convert","Now","Embed agents into the execution base and re-price it from FTE to outcome. Convert the economics, don’t defend on price."],
        ["H2 · Build the new core","12–24 mo","Productise DecisionOps per value stream and stand up Development & Regulatory AI — the white-space bet."],
        ["H3 · Compound the moat","Venture","Trust / verification infrastructure and new recurring platform revenue become the durable, high-multiple lines."]].map(([t,when,d])=>(
        <div key={t} className="fs-card" style={{padding:15}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span className="fs-h3">{t}</span><span className="fs-chip">{when}</span></div>
          <p style={{fontSize:12.5,color:"var(--ink-soft)",marginTop:8}}>{d}</p>
        </div>))}
    </div>
    <div className="fs-eyebrow" style={{marginBottom:10}}>Demand pools the new revenue points at</div>
    <div className="fs-card" style={{padding:4}}>
      {Object.entries(POOLS).map(([k,p],i)=>(
        <div key={k} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"11px 14px",borderTop:i?"1px solid var(--line)":"none",gap:12}}>
          <span style={{fontSize:13,fontWeight:650}}>{p.label}</span>
          <span className="fs-num" style={{fontSize:11.5,color:"var(--ink-soft)",textAlign:"right"}}>{p.traj}</span>
        </div>))}
    </div>
  </div>);
}
function Quad({ w,on,go,target }){
  return (<div className="fs-quad" data-target={target?"1":"0"} onClick={go} style={{outline:on?"2px solid var(--ink)":"none"}}>
    <div className="fs-h3" style={{color:target?"var(--accent-deep)":"var(--ink)"}}>{w.t}</div>
    <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:5,display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden"}}>{w.d}</div>
  </div>);
}

/* ---------- Capabilities — editable, persisted card grid ----------
   The one tab that owns the persisted card set. Every field is editable;
   create / update / delete / export / import all hit /zs/api/cards and refetch.
   Edits flow into `lines`, so the simulator, moats and charts read them too. */
const MOAT_KEYS=["ground","compliance","switching","trust","convenience"];
const SWATCHES=["var(--s1)","var(--s2)","var(--s3)","var(--s4)","var(--s5)","var(--s6)"];
function blankCard(){ return { name:"New capability area", pool:"commercial", model:"hybrid", size:0.3, start:2, attain:55,
  color:SWATCHES[0], buyer:"", moat:"", rationale:"", moats:{ground:1,compliance:1,switching:1,trust:1,convenience:1}, enabled:true }; }

function BuildView({ lines,setLines,cardsStatus,refreshCards }){
  const [editing,setEditing]=useState(null);   // card id being edited, or "__new__"
  const [draft,setDraft]=useState(null);
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState("");
  const fileRef=useRef(null);

  const startEdit=(c)=>{ setErr(""); setEditing(c.id); setDraft({...c,moats:{...(c.moats||{})}}); };
  const startNew=()=>{ setErr(""); setEditing("__new__"); setDraft(blankCard()); };
  const cancel=()=>{ setEditing(null); setDraft(null); setErr(""); };
  const setField=(k,v)=>setDraft(d=>({...d,[k]:v}));
  const setMoat=(k,v)=>setDraft(d=>({...d,moats:{...d.moats,[k]:v}}));

  async function save(){
    setBusy(true); setErr("");
    try{
      if(editing==="__new__") await apiWrite("POST",CARDS_API,cardForApi(draft));
      else await apiWrite("PUT",`${CARDS_API}/${encodeURIComponent(editing)}`,cardForApi(draft));
      const c=await refreshCards();
      if(c===null){ // API offline — apply locally so the deck still reflects the edit
        setLines(p=> editing==="__new__" ? [...p,normCard(draft)] : p.map(l=>l.id===editing?normCard({...draft,id:editing}):l));
      }
      cancel();
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  async function remove(c){
    if(!window.confirm(`Delete “${c.name}”? This can't be undone.`)) return;
    setBusy(true); setErr("");
    try{ await apiWrite("DELETE",`${CARDS_API}/${encodeURIComponent(c.id)}`);
      const r=await refreshCards();
      if(r===null) setLines(p=>p.filter(l=>l.id!==c.id));
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  function exportCards(){
    const blob=new Blob([JSON.stringify({cards:lines.map(cardForApi)},null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob); const a=document.createElement("a");
    a.href=url; a.download="zs_capability_cards.json"; a.click(); URL.revokeObjectURL(url);
  }
  async function onImportFile(e){
    const f=e.target.files&&e.target.files[0]; if(!f) return;
    setBusy(true); setErr("");
    try{ const text=await f.text(); const payload=JSON.parse(text);
      await apiWrite("POST",`${CARDS_API}/import`,payload); await refreshCards(); }
    catch(ex){ setErr("Import failed: "+ex.message); }
    finally{ setBusy(false); if(fileRef.current) fileRef.current.value=""; }
  }

  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16,flexWrap:"wrap"}}>
        <div style={{maxWidth:680}}>
          <div className="fs-eyebrow">Capability areas · editable & persisted</div>
          <div className="fs-h2" style={{marginTop:7}}>The portfolio you can edit.</div>
          <p style={{fontSize:13,color:"var(--ink-soft)",marginTop:8}}>Add, edit and delete capability areas. Changes are saved to a JSON file on the server and flow straight into the bridge, moats and charts. {cardsStatus==="offline" && <span style={{color:"var(--risk)"}}>API unreachable — showing the built-in set; edits are local only.</span>}{cardsStatus==="loading" && <span style={{color:"var(--ink-faint)"}}>Loading…</span>}</p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <button className="fs-btn" data-variant="accent" onClick={startNew} disabled={busy||editing!==null}>+ Add capability</button>
          <button className="fs-btn" data-variant="ghost" onClick={exportCards} disabled={busy}>Export JSON</button>
          <button className="fs-btn" data-variant="ghost" onClick={()=>fileRef.current&&fileRef.current.click()} disabled={busy}>Import JSON</button>
          <input ref={fileRef} type="file" accept="application/json,.json" onChange={onImportFile} style={{display:"none"}}/>
        </div>
      </div>
      {err && <div style={{marginTop:12,fontSize:12,color:"var(--risk)",fontFamily:"var(--mono)"}}>{err}</div>}
    </div>

    {editing==="__new__" && <CardEditor draft={draft} setField={setField} setMoat={setMoat} onSave={save} onCancel={cancel} busy={busy} isNew/>}

    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(330px,1fr))",gap:12}}>
      {lines.map(c=>(
        editing===c.id
          ? <CardEditor key={c.id} draft={draft} setField={setField} setMoat={setMoat} onSave={save} onCancel={cancel} busy={busy}/>
          : <CardTile key={c.id} c={c} onEdit={()=>startEdit(c)} onDelete={()=>remove(c)} disabled={busy||editing!==null}/>
      ))}
    </div>
  </div>);
}

function CardTile({ c,onEdit,onDelete,disabled }){
  const mv=c.moats||getMoats(c);
  return (<div className="fs-card" style={{padding:16,opacity:c.enabled===false?0.55:1}}>
    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:10}}>
      <span style={{width:12,height:12,borderRadius:3,background:c.color,flexShrink:0}}/>
      <div style={{flex:1,minWidth:0}}>
        <div className="fs-h3">{c.name}</div>
        <div style={{fontSize:11,color:"var(--ink-faint)"}}>{POOLS[c.pool]?.label} · {MODELS[c.model]?.label}</div>
      </div>
      <span className="fs-chip" style={{borderColor:QUALITY_COLORS[MODELS[c.model]?.quality],color:QUALITY_COLORS[MODELS[c.model]?.quality]}}>{QUALITY_LABELS[MODELS[c.model]?.quality]}</span>
    </div>
    <div style={{display:"flex",gap:14,marginBottom:10}}>
      <span className="fs-num" style={{fontSize:12,color:"var(--ink-soft)"}}>size <b style={{color:"var(--ink)"}}>${(c.size??0).toFixed(2)}B</b></span>
      <span className="fs-num" style={{fontSize:12,color:"var(--ink-soft)"}}>ramp <b style={{color:"var(--ink)"}}>Y{c.start}</b></span>
      <span className="fs-num" style={{fontSize:12,color:"var(--ink-soft)"}}>win <b style={{color:(c.attain??60)<55?"var(--risk)":"var(--ink)"}}>{c.attain??60}%</b></span>
    </div>
    {c.buyer && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginBottom:4}}><span className="fs-eyebrow">Buyer</span> {c.buyer}</div>}
    {c.moat && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginBottom:4}}><span className="fs-eyebrow">Moat</span> {c.moat}</div>}
    {c.rationale && <p style={{fontSize:12,color:"var(--ink-soft)",margin:"8px 0 0"}}>{c.rationale}</p>}
    <div style={{display:"flex",gap:7,marginTop:10,flexWrap:"wrap"}}>
      {MOAT_KEYS.map(k=>(<span key={k} className="fs-chip" title={MOAT_DIMS[k].label}>{MOAT_DIMS[k].short} {mv[k]??0}</span>))}
    </div>
    <div style={{display:"flex",gap:8,marginTop:14,borderTop:"1px solid var(--line)",paddingTop:12}}>
      <button className="fs-btn" data-variant="ghost" style={{padding:"7px 12px",fontSize:12}} onClick={onEdit} disabled={disabled}>Edit</button>
      <button className="fs-btn" data-variant="risk" style={{padding:"7px 12px",fontSize:12}} onClick={onDelete} disabled={disabled}>Delete</button>
    </div>
  </div>);
}

function CardEditor({ draft,setField,setMoat,onSave,onCancel,busy,isNew }){
  return (<div className="fs-card fs-fade" style={{padding:18,marginBottom:isNew?18:0,gridColumn:isNew?undefined:"1 / -1",borderColor:"var(--accent)"}}>
    <div className="fs-eyebrow" style={{marginBottom:12}}>{isNew?"New capability area":"Editing — "+draft.name}</div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:14}}>
      <Field label="Name"><input type="text" value={draft.name} onChange={e=>setField("name",e.target.value)}/></Field>
      <Field label="Demand pool"><select value={draft.pool} onChange={e=>setField("pool",e.target.value)}>{Object.entries(POOLS).map(([k,p])=><option key={k} value={k}>{p.label}</option>)}</select></Field>
      <Field label="Commercial model"><select value={draft.model} onChange={e=>setField("model",e.target.value)}>{Object.entries(MODELS).map(([k,m])=><option key={k} value={k}>{m.label}</option>)}</select></Field>
      <Field label="Target buyer"><input type="text" value={draft.buyer||""} onChange={e=>setField("buyer",e.target.value)}/></Field>
      <Field label="Colour"><select value={draft.color} onChange={e=>setField("color",e.target.value)}>{SWATCHES.map((s,i)=><option key={s} value={s}>Series {i+1}</option>)}</select></Field>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:14,marginTop:8}}>
      <Slider label="Year-H revenue size" value={draft.size} min={0} max={1} step={0.05} onChange={v=>setField("size",v)} fmt={v=>`$${v.toFixed(2)}B`}/>
      <Slider label="Ramp begins" value={draft.start} min={1} max={8} step={1} onChange={v=>setField("start",Math.round(v))} fmt={v=>`Year ${v}`}/>
      <Slider label="Win-probability" value={draft.attain} min={10} max={95} step={5} onChange={v=>setField("attain",Math.round(v))} fmt={v=>`${v}%`} tone={draft.attain<55?"risk":undefined}/>
    </div>
    <div style={{marginTop:8}}>
      <div className="fs-eyebrow" style={{marginBottom:8}}>Moat scores (0–3)</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:14}}>
        {MOAT_KEYS.map(k=>(<Slider key={k} label={MOAT_DIMS[k].short} value={draft.moats?.[k]??0} min={0} max={3} step={1} onChange={v=>setMoat(k,Math.round(v))} fmt={v=>`${v}/3`}/>))}
      </div>
    </div>
    <Field label="Source of moat (one line)"><input type="text" value={draft.moat||""} onChange={e=>setField("moat",e.target.value)}/></Field>
    <div style={{marginBottom:12}}>
      <div style={{fontSize:11.5,color:"var(--ink-soft)",fontWeight:600,marginBottom:5}}>Rationale</div>
      <textarea value={draft.rationale||""} onChange={e=>setField("rationale",e.target.value)} rows={3}
        style={{fontFamily:"var(--sans)",fontSize:13,padding:"8px 10px",border:"1px solid var(--line-strong)",borderRadius:8,background:"var(--surface)",color:"var(--ink)",width:"100%",resize:"vertical"}}/>
    </div>
    <div style={{display:"flex",gap:8}}>
      <button className="fs-btn" data-variant="accent" onClick={onSave} disabled={busy||!draft.name.trim()}>{busy?"Saving…":"Save"}</button>
      <button className="fs-btn" data-variant="ghost" onClick={onCancel} disabled={busy}>Cancel</button>
    </div>
  </div>);
}

/* ---------- Constructs — editable, persisted "how we charge" grid ----------
   Mirrors BuildView: inline-edit every field, add, delete-with-confirm, export,
   import — all against /zs/api/constructs with an offline fallback to the
   baked-in DEFAULT_CONSTRUCTS. */
function blankConstruct(){ return { name:"New construct", meter:"", value_story:"", quality:"", buyer:"", zs_risk:"", fit:"", examples:"" }; }

function ConstructsView({ constructs,setConstructs,constructsStatus,refreshConstructs }){
  const [editing,setEditing]=useState(null);
  const [draft,setDraft]=useState(null);
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState("");
  const fileRef=useRef(null);

  const startEdit=(c)=>{ setErr(""); setEditing(c.id); setDraft({...c}); };
  const startNew=()=>{ setErr(""); setEditing("__new__"); setDraft(blankConstruct()); };
  const cancel=()=>{ setEditing(null); setDraft(null); setErr(""); };
  const setField=(k,v)=>setDraft(d=>({...d,[k]:v}));

  async function save(){
    setBusy(true); setErr("");
    try{
      if(editing==="__new__") await apiWrite("POST",CONSTRUCTS_API,draft);
      else await apiWrite("PUT",`${CONSTRUCTS_API}/${encodeURIComponent(editing)}`,draft);
      const c=await refreshConstructs();
      if(c===null){ setConstructs(p=> editing==="__new__" ? [...p,draft] : p.map(l=>l.id===editing?{...draft,id:editing}:l)); }
      cancel();
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  async function remove(c){
    if(!window.confirm(`Delete “${c.name}”? This can't be undone.`)) return;
    setBusy(true); setErr("");
    try{ await apiWrite("DELETE",`${CONSTRUCTS_API}/${encodeURIComponent(c.id)}`);
      const r=await refreshConstructs();
      if(r===null) setConstructs(p=>p.filter(l=>l.id!==c.id));
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  function exportCards(){
    const blob=new Blob([JSON.stringify({cards:constructs},null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob); const a=document.createElement("a");
    a.href=url; a.download="zs_commercial_constructs.json"; a.click(); URL.revokeObjectURL(url);
  }
  async function onImportFile(e){
    const f=e.target.files&&e.target.files[0]; if(!f) return;
    setBusy(true); setErr("");
    try{ const payload=JSON.parse(await f.text());
      await apiWrite("POST",`${CONSTRUCTS_API}/import`,payload); await refreshConstructs(); }
    catch(ex){ setErr("Import failed: "+ex.message); }
    finally{ setBusy(false); if(fileRef.current) fileRef.current.value=""; }
  }

  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16,flexWrap:"wrap"}}>
        <div style={{maxWidth:680}}>
          <div className="fs-eyebrow">Commercial constructs · editable & persisted</div>
          <div className="fs-h2" style={{marginTop:7}}>How we charge.</div>
          <p style={{fontSize:13,color:"var(--ink-soft)",marginTop:8}}>The metering structures behind the offerings — each names what it meters, the value story, the buyer and the ZS risk. Saved to a JSON file on the server. {constructsStatus==="offline" && <span style={{color:"var(--risk)"}}>API unreachable — showing the built-in set; edits are local only.</span>}{constructsStatus==="loading" && <span style={{color:"var(--ink-faint)"}}>Loading…</span>}</p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <button className="fs-btn" data-variant="accent" onClick={startNew} disabled={busy||editing!==null}>+ Add construct</button>
          <button className="fs-btn" data-variant="ghost" onClick={exportCards} disabled={busy}>Export JSON</button>
          <button className="fs-btn" data-variant="ghost" onClick={()=>fileRef.current&&fileRef.current.click()} disabled={busy}>Import JSON</button>
          <input ref={fileRef} type="file" accept="application/json,.json" onChange={onImportFile} style={{display:"none"}}/>
        </div>
      </div>
      {err && <div style={{marginTop:12,fontSize:12,color:"var(--risk)",fontFamily:"var(--mono)"}}>{err}</div>}
    </div>

    {editing==="__new__" && <ConstructEditor draft={draft} setField={setField} onSave={save} onCancel={cancel} busy={busy} isNew/>}

    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(330px,1fr))",gap:12}}>
      {constructs.map(c=>(
        editing===c.id
          ? <ConstructEditor key={c.id} draft={draft} setField={setField} onSave={save} onCancel={cancel} busy={busy}/>
          : <ConstructTile key={c.id} c={c} onEdit={()=>startEdit(c)} onDelete={()=>remove(c)} disabled={busy||editing!==null}/>
      ))}
    </div>
  </div>);
}

function ConstructTile({ c,onEdit,onDelete,disabled }){
  const q=c.quality||"";
  return (<div className="fs-card" style={{padding:16}}>
    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:10}}>
      <div style={{flex:1,minWidth:0}}><div className="fs-h3">{c.name}</div></div>
      {q && <span className="fs-chip" style={{borderColor:QUALITY_COLORS[q],color:QUALITY_COLORS[q]}}>{QUALITY_LABELS[q]}</span>}
    </div>
    {c.meter && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginBottom:4}}><span className="fs-eyebrow">Meters</span> {c.meter}</div>}
    {c.value_story && <p style={{fontSize:12,color:"var(--ink-soft)",margin:"8px 0 0"}}>{c.value_story}</p>}
    {c.buyer && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:8}}><span className="fs-eyebrow">Buyer</span> {c.buyer}</div>}
    {c.zs_risk && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:4}}><span className="fs-eyebrow" style={{color:"var(--risk)"}}>ZS risk</span> {c.zs_risk}</div>}
    {c.fit && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:4}}><span className="fs-eyebrow">Fit</span> {c.fit}</div>}
    {c.examples && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:4}}><span className="fs-eyebrow">Examples</span> {c.examples}</div>}
    <div style={{display:"flex",gap:8,marginTop:14,borderTop:"1px solid var(--line)",paddingTop:12}}>
      <button className="fs-btn" data-variant="ghost" style={{padding:"7px 12px",fontSize:12}} onClick={onEdit} disabled={disabled}>Edit</button>
      <button className="fs-btn" data-variant="risk" style={{padding:"7px 12px",fontSize:12}} onClick={onDelete} disabled={disabled}>Delete</button>
    </div>
  </div>);
}

function ConstructEditor({ draft,setField,onSave,onCancel,busy,isNew }){
  return (<div className="fs-card fs-fade" style={{padding:18,marginBottom:isNew?18:0,gridColumn:isNew?undefined:"1 / -1",borderColor:"var(--accent)"}}>
    <div className="fs-eyebrow" style={{marginBottom:12}}>{isNew?"New construct":"Editing — "+draft.name}</div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:14}}>
      <Field label="Name"><input type="text" value={draft.name} onChange={e=>setField("name",e.target.value)}/></Field>
      <Field label="Revenue quality"><select value={draft.quality||""} onChange={e=>setField("quality",e.target.value)}><option value="">— unset —</option>{CONSTRUCT_QUALITIES.map(q=><option key={q} value={q}>{QUALITY_LABELS[q]}</option>)}</select></Field>
      <Field label="Target buyer"><input type="text" value={draft.buyer||""} onChange={e=>setField("buyer",e.target.value)}/></Field>
    </div>
    <Field label="What it meters"><input type="text" value={draft.meter||""} onChange={e=>setField("meter",e.target.value)}/></Field>
    <ProseField label="Value story" value={draft.value_story} onChange={v=>setField("value_story",v)} rows={3}/>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <ProseField label="ZS risk" value={draft.zs_risk} onChange={v=>setField("zs_risk",v)} rows={2}/>
      <ProseField label="Where it fits" value={draft.fit} onChange={v=>setField("fit",v)} rows={2}/>
    </div>
    <ProseField label="Examples" value={draft.examples} onChange={v=>setField("examples",v)} rows={2}/>
    <div style={{display:"flex",gap:8,marginTop:4}}>
      <button className="fs-btn" data-variant="accent" onClick={onSave} disabled={busy||!draft.name.trim()}>{busy?"Saving…":"Save"}</button>
      <button className="fs-btn" data-variant="ghost" onClick={onCancel} disabled={busy}>Cancel</button>
    </div>
  </div>);
}

/* ---------- Bets — editable, persisted "where we place big chips" grid ----------
   Mirrors BuildView for the bet field shape; offline fallback to DEFAULT_BETS. */
function blankBet(){ return { name:"New bet", thesis:"", unit_moat:"", kill_criterion:"", ceiling:"", horizon:"", posture:"", native:true }; }

function BetsView({ bets,setBets,betsStatus,refreshBets }){
  const [editing,setEditing]=useState(null);
  const [draft,setDraft]=useState(null);
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState("");
  const fileRef=useRef(null);

  const startEdit=(c)=>{ setErr(""); setEditing(c.id); setDraft({...c}); };
  const startNew=()=>{ setErr(""); setEditing("__new__"); setDraft(blankBet()); };
  const cancel=()=>{ setEditing(null); setDraft(null); setErr(""); };
  const setField=(k,v)=>setDraft(d=>({...d,[k]:v}));

  async function save(){
    setBusy(true); setErr("");
    try{
      if(editing==="__new__") await apiWrite("POST",BETS_API,draft);
      else await apiWrite("PUT",`${BETS_API}/${encodeURIComponent(editing)}`,draft);
      const c=await refreshBets();
      if(c===null){ setBets(p=> editing==="__new__" ? [...p,draft] : p.map(l=>l.id===editing?{...draft,id:editing}:l)); }
      cancel();
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  async function remove(c){
    if(!window.confirm(`Delete “${c.name}”? This can't be undone.`)) return;
    setBusy(true); setErr("");
    try{ await apiWrite("DELETE",`${BETS_API}/${encodeURIComponent(c.id)}`);
      const r=await refreshBets();
      if(r===null) setBets(p=>p.filter(l=>l.id!==c.id));
    }catch(e){ setErr(e.message); }
    finally{ setBusy(false); }
  }
  function exportCards(){
    const blob=new Blob([JSON.stringify({cards:bets},null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob); const a=document.createElement("a");
    a.href=url; a.download="zs_capability_bets.json"; a.click(); URL.revokeObjectURL(url);
  }
  async function onImportFile(e){
    const f=e.target.files&&e.target.files[0]; if(!f) return;
    setBusy(true); setErr("");
    try{ const payload=JSON.parse(await f.text());
      await apiWrite("POST",`${BETS_API}/import`,payload); await refreshBets(); }
    catch(ex){ setErr("Import failed: "+ex.message); }
    finally{ setBusy(false); if(fileRef.current) fileRef.current.value=""; }
  }

  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16,flexWrap:"wrap"}}>
        <div style={{maxWidth:680}}>
          <div className="fs-eyebrow">Capability bets · editable & persisted</div>
          <div className="fs-h2" style={{marginTop:7}}>Where we place big chips.</div>
          <p style={{fontSize:13,color:"var(--ink-soft)",marginTop:8}}>The frontier wagers — each carries a thesis, the unit of moat, an explicit kill-criterion and a posture (build / partner / consume). Saved to a JSON file on the server. {betsStatus==="offline" && <span style={{color:"var(--risk)"}}>API unreachable — showing the built-in set; edits are local only.</span>}{betsStatus==="loading" && <span style={{color:"var(--ink-faint)"}}>Loading…</span>}</p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <button className="fs-btn" data-variant="accent" onClick={startNew} disabled={busy||editing!==null}>+ Add bet</button>
          <button className="fs-btn" data-variant="ghost" onClick={exportCards} disabled={busy}>Export JSON</button>
          <button className="fs-btn" data-variant="ghost" onClick={()=>fileRef.current&&fileRef.current.click()} disabled={busy}>Import JSON</button>
          <input ref={fileRef} type="file" accept="application/json,.json" onChange={onImportFile} style={{display:"none"}}/>
        </div>
      </div>
      {err && <div style={{marginTop:12,fontSize:12,color:"var(--risk)",fontFamily:"var(--mono)"}}>{err}</div>}
    </div>

    {editing==="__new__" && <BetEditor draft={draft} setField={setField} onSave={save} onCancel={cancel} busy={busy} isNew/>}

    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(330px,1fr))",gap:12}}>
      {bets.map(c=>(
        editing===c.id
          ? <BetEditor key={c.id} draft={draft} setField={setField} onSave={save} onCancel={cancel} busy={busy}/>
          : <BetTile key={c.id} c={c} onEdit={()=>startEdit(c)} onDelete={()=>remove(c)} disabled={busy||editing!==null}/>
      ))}
    </div>
  </div>);
}

function BetTile({ c,onEdit,onDelete,disabled }){
  const p=c.posture||"";
  return (<div className="fs-card" style={{padding:16,opacity:c.native===false?0.72:1}}>
    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:10}}>
      <div style={{flex:1,minWidth:0}}>
        <div className="fs-h3">{c.name}</div>
        {(c.horizon||c.ceiling) && <div style={{fontSize:11,color:"var(--ink-faint)"}}>{c.horizon?HORIZON_LABELS[c.horizon]:""}{c.horizon&&c.ceiling?" · ":""}{c.ceiling?`ceiling ${c.ceiling}`:""}</div>}
      </div>
      {p && <span className="fs-chip" style={{borderColor:POSTURE_COLORS[p],color:POSTURE_COLORS[p]}}>{POSTURE_LABELS[p]}</span>}
    </div>
    <div style={{display:"flex",gap:7,marginBottom:8,flexWrap:"wrap"}}>
      <span className="fs-chip">{c.native===false?"Not ZS-native":"ZS-native"}</span>
    </div>
    {c.thesis && <p style={{fontSize:12,color:"var(--ink-soft)",margin:"8px 0 0"}}>{c.thesis}</p>}
    {c.unit_moat && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:8}}><span className="fs-eyebrow">Unit / moat</span> {c.unit_moat}</div>}
    {c.kill_criterion && <div style={{fontSize:11.5,color:"var(--ink-soft)",marginTop:4}}><span className="fs-eyebrow" style={{color:"var(--risk)"}}>Kill if</span> {c.kill_criterion}</div>}
    <div style={{display:"flex",gap:8,marginTop:14,borderTop:"1px solid var(--line)",paddingTop:12}}>
      <button className="fs-btn" data-variant="ghost" style={{padding:"7px 12px",fontSize:12}} onClick={onEdit} disabled={disabled}>Edit</button>
      <button className="fs-btn" data-variant="risk" style={{padding:"7px 12px",fontSize:12}} onClick={onDelete} disabled={disabled}>Delete</button>
    </div>
  </div>);
}

function BetEditor({ draft,setField,onSave,onCancel,busy,isNew }){
  return (<div className="fs-card fs-fade" style={{padding:18,marginBottom:isNew?18:0,gridColumn:isNew?undefined:"1 / -1",borderColor:"var(--accent)"}}>
    <div className="fs-eyebrow" style={{marginBottom:12}}>{isNew?"New bet":"Editing — "+draft.name}</div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:14}}>
      <Field label="Name"><input type="text" value={draft.name} onChange={e=>setField("name",e.target.value)}/></Field>
      <Field label="Horizon"><select value={draft.horizon||""} onChange={e=>setField("horizon",e.target.value)}><option value="">— unset —</option>{BET_HORIZONS.map(h=><option key={h} value={h}>{HORIZON_LABELS[h]}</option>)}</select></Field>
      <Field label="Posture"><select value={draft.posture||""} onChange={e=>setField("posture",e.target.value)}><option value="">— unset —</option>{BET_POSTURES.map(s=><option key={s} value={s}>{POSTURE_LABELS[s]}</option>)}</select></Field>
      <Field label="Revenue ceiling"><input type="text" value={draft.ceiling||""} onChange={e=>setField("ceiling",e.target.value)}/></Field>
    </div>
    <div style={{marginBottom:12}}>
      <label style={{display:"flex",alignItems:"center",gap:8,fontSize:12.5,color:"var(--ink-soft)",fontWeight:600,cursor:"pointer"}}>
        <input type="checkbox" checked={draft.native!==false} onChange={e=>setField("native",e.target.checked)} style={{width:"auto"}}/>
        ZS-native build (uncheck if it's a partner/consume play)
      </label>
    </div>
    <ProseField label="Thesis" value={draft.thesis} onChange={v=>setField("thesis",v)} rows={3}/>
    <ProseField label="Unit of value / source of moat" value={draft.unit_moat} onChange={v=>setField("unit_moat",v)} rows={2}/>
    <ProseField label="Kill-criterion" value={draft.kill_criterion} onChange={v=>setField("kill_criterion",v)} rows={2}/>
    <div style={{display:"flex",gap:8,marginTop:4}}>
      <button className="fs-btn" data-variant="accent" onClick={onSave} disabled={busy||!draft.name.trim()}>{busy?"Saving…":"Save"}</button>
      <button className="fs-btn" data-variant="ghost" onClick={onCancel} disabled={busy}>Cancel</button>
    </div>
  </div>);
}

// Shared multi-line prose field (used by the constructs + bets editors).
function ProseField({ label,value,onChange,rows }){
  return (<div style={{marginBottom:12}}>
    <div style={{fontSize:11.5,color:"var(--ink-soft)",fontWeight:600,marginBottom:5}}>{label}</div>
    <textarea value={value||""} onChange={e=>onChange(e.target.value)} rows={rows||3}
      style={{fontFamily:"var(--sans)",fontSize:13,padding:"8px 10px",border:"1px solid var(--line-strong)",borderRadius:8,background:"var(--surface)",color:"var(--ink)",width:"100%",resize:"vertical"}}/>
  </div>);
}

/* ---------- Risk-adjusted simulator ---------- */
function SimView({ base,setBase,erosion,setErosion,shape,setShape,target,setTarget,H,setH,lines,setLines,model,fmtB,saveScenario,resetScenario,saved,risk }){
  const setLine=(id,patch)=>setLines(p=>p.map(l=>l.id===id?{...l,...patch}:l));
  const mixData=[{name:"core",value:model.mix.core},{name:"recurring",value:model.mix.recurring},{name:"outcome",value:model.mix.outcome},{name:"project",value:model.mix.project}].filter(d=>d.value>0.001);
  const bandMax=Math.max(target,model.p90,model.grossLanding)*1.1;
  return (
    <div className="fs-fade" style={{display:"grid",gridTemplateColumns:"320px 1fr",gap:18,alignItems:"start"}}>
      <div className="fs-card" style={{padding:18,position:"sticky",top:150}}>
        <div className="fs-eyebrow" style={{marginBottom:12}}>Scenario inputs</div>
        <Slider label="Base revenue today" value={base} min={1} max={4} step={0.1} onChange={setBase} fmt={fmtB}/>
        <Slider label="Legacy erosion over horizon" value={erosion} min={0} max={80} step={5} onChange={setErosion} fmt={v=>`${v}%`}/>
        <Slider label="Erosion shape" value={shape} min={0.6} max={3} step={0.1} onChange={setShape} fmt={v=>v>1.4?"Front-loaded":v<0.9?"Back-loaded":"Linear"}/>
        <Slider label="Target revenue" value={target} min={base} max={6} step={0.1} onChange={setTarget} fmt={fmtB}/>
        <Slider label="Horizon" value={H} min={3} max={8} step={1} onChange={setH} fmt={v=>`${v} yrs`}/>
        <hr className="fs-rule" style={{margin:"12px 0"}}/>
        <div className="fs-eyebrow" style={{marginBottom:10}}>Risk &amp; competition</div>
        <Slider label="Competitive compression (new lines)" value={risk.compression} min={0} max={45} step={1} onChange={risk.setCompression} fmt={v=>`${v}%`} tone="risk"/>
        <Slider label="Outcome dispute / clawback" value={risk.haircut} min={0} max={30} step={1} onChange={risk.setHaircut} fmt={v=>`${v}%`} tone="risk"/>
        <Slider label="Outcome cash lag" value={risk.cashLag} min={0} max={3} step={1} onChange={risk.setCashLag} fmt={v=>`${v} yr`} tone="risk"/>
        <Slider label="Execution discount (all lines)" value={risk.execDiscount} min={0} max={40} step={1} onChange={risk.setExecDiscount} fmt={v=>`${v}%`} tone="risk"/>
        <hr className="fs-rule" style={{margin:"12px 0"}}/>
        <div style={{display:"flex",gap:8}}>
          <button className="fs-btn" data-variant="accent" style={{flex:1}} onClick={saveScenario}>{saved?"Saved":"Save scenario"}</button>
          <button className="fs-btn" data-variant="ghost" onClick={resetScenario}>Reset</button>
        </div>
      </div>

      <div>
        <div className="fs-card" style={{padding:18,marginBottom:16,display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14}}>
          <Stat label="Surviving core" value={model.survivor.toFixed(2)} unit="B"/>
          <Stat label="Expected landing" value={model.landing.toFixed(2)} unit="B" tone="accent" sub={`gross ${fmtB(model.grossLanding)}`}/>
          <Stat label="Year-H cash" value={model.cashLanding.toFixed(2)} unit="B" tone="risk" sub={`vs recognised ${fmtB(model.landing)}`}/>
          <Stat label="Margin at Year H" value={model.marginH} unit="%" tone="good" sub={`trough ${model.marginTrough}%`}/>
        </div>

        <div className="fs-card" style={{padding:"18px 14px 8px",marginBottom:16}}>
          <div style={{display:"flex",justifyContent:"space-between",padding:"0 6px",marginBottom:4}}>
            <span className="fs-eyebrow">Risk-adjusted bridge — recognised vs cash</span>
            <span className="fs-num" style={{fontSize:11.5,color:"var(--risk)"}}>rev dip {fmtB(model.tr.v)} Y{model.tr.y} · cash dip {fmtB(model.ctr.v)} Y{model.ctr.y}</span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={model.data} margin={{top:8,right:14,left:0,bottom:4}}>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--line)" vertical={false}/>
              <XAxis dataKey="year" tick={{fontSize:11,fontFamily:"var(--mono)",fill:"var(--ink-faint)"}} tickFormatter={y=>`Y${y}`} axisLine={{stroke:"var(--line-strong)"}} tickLine={false}/>
              <YAxis tick={{fontSize:11,fontFamily:"var(--mono)",fill:"var(--ink-faint)"}} tickFormatter={v=>v.toFixed(1)} axisLine={false} tickLine={false} width={34} domain={[0,Math.max(target,model.grossLanding)*1.12]}/>
              <Tooltip content={<BuildTip/>}/>
              <Area type="monotone" dataKey="legacy" stackId="1" stroke="var(--core)" fill="var(--core)" fillOpacity={0.16} name="Transformed core"/>
              {model.enabled.map(l=>(<Area key={l.id} type="monotone" dataKey={l.id} stackId="1" stroke={l.color} fill={l.color} fillOpacity={0.5} name={l.name}/>))}
              <Line type="monotone" dataKey="cash" stroke="var(--cash)" strokeWidth={2} strokeDasharray="4 3" dot={false} name="Cash collected"/>
              <ReferenceLine y={target} stroke="var(--accent)" strokeDasharray="5 4" strokeWidth={1.5} label={{value:`target ${target.toFixed(1)}`,position:"right",fontSize:10,fill:"var(--accent-deep)",fontFamily:"var(--mono)"}}/>
              <ReferenceLine y={base} stroke="var(--ink-faint)" strokeDasharray="2 3" label={{value:"today",position:"right",fontSize:10,fill:"var(--ink-faint)",fontFamily:"var(--mono)"}}/>
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:16,marginBottom:16}}>
          {/* outcome range */}
          <div className="fs-card" style={{padding:16}}>
            <div className="fs-eyebrow" style={{marginBottom:12}}>Outcome range · 500 runs</div>
            <RangeBar p10={model.p10} p50={model.p50} p90={model.p90} target={target} max={bandMax} fmtB={fmtB}/>
            <div style={{marginTop:14,textAlign:"center"}}>
              <div className="fs-num" style={{fontSize:22,fontWeight:700,color:model.pHit>=60?"var(--good)":model.pHit>=35?"var(--accent)":"var(--risk)"}}>{model.pHit}%</div>
              <div className="fs-eyebrow" style={{marginTop:2}}>chance of hitting target</div>
            </div>
          </div>
          {/* margin J-curve */}
          <div className="fs-card" style={{padding:16}}>
            <div className="fs-eyebrow" style={{marginBottom:8}}>Blended margin · the J-curve</div>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={model.marginData} margin={{top:6,right:8,left:-14,bottom:0}}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--line)" vertical={false}/>
                <XAxis dataKey="year" tick={{fontSize:10,fontFamily:"var(--mono)",fill:"var(--ink-faint)"}} tickFormatter={y=>`Y${y}`} axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:10,fontFamily:"var(--mono)",fill:"var(--ink-faint)"}} tickFormatter={v=>`${v}%`} axisLine={false} tickLine={false} width={38}/>
                <ReferenceLine y={0} stroke="var(--line-strong)"/>
                <Tooltip formatter={v=>`${v}%`} labelFormatter={y=>`Year ${y}`} contentStyle={{fontSize:12,borderRadius:8,border:"1px solid var(--line)"}}/>
                <Line type="monotone" dataKey="margin" stroke="var(--accent)" strokeWidth={2.5} dot={{r:2}}/>
              </LineChart>
            </ResponsiveContainer>
          </div>
          {/* quality mix */}
          <div className="fs-card" style={{padding:16}}>
            <div className="fs-eyebrow" style={{marginBottom:6}}>Revenue quality at Year H</div>
            <ResponsiveContainer width="100%" height={150}>
              <PieChart><Pie data={mixData} dataKey="value" nameKey="name" innerRadius={36} outerRadius={60} paddingAngle={2} stroke="none">
                {mixData.map(d=><Cell key={d.name} fill={QUALITY_COLORS[d.name]}/>)}</Pie>
                <Tooltip content={<MixTip/>}/></PieChart>
            </ResponsiveContainer>
            <div style={{display:"flex",flexWrap:"wrap",gap:7,justifyContent:"center",marginTop:2}}>
              {mixData.map(d=>(<span key={d.name} style={{display:"flex",alignItems:"center",gap:4,fontSize:10.5}}>
                <span style={{width:8,height:8,borderRadius:2,background:QUALITY_COLORS[d.name]}}/>{QUALITY_LABELS[d.name]}</span>))}
            </div>
          </div>
        </div>

        <div className="fs-eyebrow" style={{marginBottom:10}}>Offering portfolio — size, ramp and win-probability</div>
        <div style={{display:"grid",gap:8}}>
          {lines.map(l=>(
            <div key={l.id} className="fs-card" style={{padding:14,opacity:l.enabled?1:0.5}}>
              <div style={{display:"flex",alignItems:"center",gap:12}}>
                <span style={{width:10,height:10,borderRadius:3,background:l.color,flexShrink:0}}/>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:13,fontWeight:700}}>{l.name}</div>
                  <div style={{fontSize:11,color:"var(--ink-faint)"}}>{POOLS[l.pool]?.label} · {MODELS[l.model]?.label}</div>
                </div>
                <span className="fs-chip" style={{borderColor:QUALITY_COLORS[MODELS[l.model]?.quality],color:QUALITY_COLORS[MODELS[l.model]?.quality]}}>{QUALITY_LABELS[MODELS[l.model]?.quality]}</span>
                <button className="fs-btn" data-variant="ghost" style={{padding:"6px 10px",fontSize:12}} onClick={()=>setLine(l.id,{enabled:!l.enabled})}>{l.enabled?"On":"Off"}</button>
              </div>
              {l.enabled && (<div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:14,marginTop:12}}>
                <Slider label="Year-H revenue" value={l.size} min={0} max={1.2} step={0.05} onChange={v=>setLine(l.id,{size:v})} fmt={fmtB}/>
                <Slider label="Ramp begins" value={l.start} min={1} max={H} step={1} onChange={v=>setLine(l.id,{start:v})} fmt={v=>`Year ${v}`}/>
                <Slider label="Win-probability" value={l.attain??60} min={10} max={95} step={5} onChange={v=>setLine(l.id,{attain:v})} fmt={v=>`${v}%`} tone={(l.attain??60)<55?"risk":undefined}/>
              </div>)}
            </div>))}
        </div>
      </div>
    </div>);
}
function RangeBar({ p10,p50,p90,target,max,fmtB }){
  const pc=v=>`${clamp(v/max*100,0,100)}%`;
  return (<div>
    <div style={{position:"relative",height:30,background:"var(--surface-2)",borderRadius:6,border:"1px solid var(--line)"}}>
      <div style={{position:"absolute",left:pc(p10),width:`calc(${pc(p90)} - ${pc(p10)})`,top:6,bottom:6,background:"var(--accent-soft)",border:"1px solid var(--accent)",borderRadius:4}}/>
      <div style={{position:"absolute",left:pc(p50),top:2,bottom:2,width:2,background:"var(--accent-deep)"}}/>
      <div style={{position:"absolute",left:pc(target),top:-4,bottom:-4,width:2,background:"var(--ink)"}}/>
    </div>
    <div style={{display:"flex",justifyContent:"space-between",marginTop:7,fontSize:10.5}}>
      <span className="fs-num" style={{color:"var(--ink-soft)"}}>P10 {fmtB(p10)}</span>
      <span className="fs-num" style={{fontWeight:700}}>P50 {fmtB(p50)}</span>
      <span className="fs-num" style={{color:"var(--ink-soft)"}}>P90 {fmtB(p90)}</span>
    </div>
    <div style={{fontSize:10.5,color:"var(--ink)",marginTop:6,textAlign:"center"}}><span style={{display:"inline-block",width:10,height:2,background:"var(--ink)",verticalAlign:"middle",marginRight:5}}/>target</div>
  </div>);
}
function BuildTip({ active,payload,label }){
  if(!active||!payload) return null;
  const cash=payload.find(p=>p.dataKey==="cash");
  const stack=payload.filter(p=>p.dataKey!=="cash");
  const total=stack.reduce((s,p)=>s+(p.value||0),0);
  return (<div className="fs-card" style={{padding:10,boxShadow:"0 6px 20px rgba(0,0,0,.12)"}}>
    <div className="fs-num" style={{fontSize:12,fontWeight:700,marginBottom:6}}>Year {label} · recognised ${total.toFixed(2)}B{cash?` · cash $${(cash.value||0).toFixed(2)}B`:""}</div>
    {stack.slice().reverse().map(p=>(<div key={p.name} style={{display:"flex",alignItems:"center",gap:6,fontSize:11.5,marginBottom:2}}>
      <span style={{width:8,height:8,borderRadius:2,background:p.color}}/><span style={{flex:1,color:"var(--ink-soft)"}}>{p.name}</span><span className="fs-num">${(p.value||0).toFixed(2)}B</span></div>))}
  </div>);
}
function MixTip({ active,payload }){ if(!active||!payload||!payload.length) return null; const p=payload[0];
  return <div className="fs-card" style={{padding:"7px 10px"}}><span className="fs-num" style={{fontSize:12}}>{QUALITY_LABELS[p.name]} · ${p.value.toFixed(2)}B</span></div>; }

/* ---------- Red team ---------- */
function RedTeamView({ model, applyPreset, fmtB, risk }){
  const presets={
    base:{ label:"Base case", erosion:50, compression:8, haircut:10, cashLag:1, exec:0, note:"The plan as drawn." },
    bear:{ label:"Bear case", erosion:68, compression:22, haircut:18, cashLag:2, exec:18, note:"Faster erosion, real price competition, weak collection — the sceptic’s world." },
    squeeze:{ label:"Competitive squeeze", erosion:55, compression:38, haircut:12, cashLag:1, exec:10, note:"New lines commoditise as IQVIA, Veeva and the labs pile in." },
    exec:{ label:"Execution shortfall", erosion:55, compression:12, haircut:12, cashLag:2, exec:30, note:"M&A integration and hiring miss — the build runs slow." },
    flywheel:{ label:"Flywheel doesn’t aggregate", erosion:55, compression:24, haircut:14, cashLag:1, exec:14, note:"Client data can’t be pooled, so differentiation thins and price competition rises." },
  };
  const challenges=[
    ["Competitors don’t stand still","IQVIA already has 19/20 top pharma on its agents, NVIDIA compute and regulatory depth — a strong claim to the same wedge.","Modelled as competitive compression on the new lines. Push the slider and watch the landing fall."],
    ["The data flywheel may not turn","Cross-client aggregation is what makes ground-truth compound — pharma confidentiality may forbid it.","Re-rated ‘ground-truth’ to Contested in the moats view; the ‘flywheel doesn’t aggregate’ preset prices the consequence."],
    ["Both halves of the bridge are contested","The surviving core is exactly what MBB targets and GCCs insource; 50% erosion is optimistic.","Erosion is a dial — the bear case runs 68%."],
    ["The biggest new lines are least certain","DecisionOps and Dev/Reg AI carry half the new revenue at the lowest right-to-win.","Per-line win-probability now risk-adjusts every line; Dev/Reg AI defaults to 48%."],
    ["New revenue commoditises too","Outcome and subscription pricing get bid down.","Competitive compression now erodes the new lines, not just legacy."],
    ["Revenue ≠ cash","Outcome revenue is delayed, disputed, clawed back.","Cash line, dispute haircut and collection lag added — the cash trough is deeper and later."],
    ["Margins are a J-curve, not a lift","Immature managed-service lines run thin or negative early.","Blended margin now dips before it recovers; watch the trough."],
    ["False precision","A single landing number overstates confidence.","500-run Monte Carlo gives P10/P50/P90 and a probability of hitting target."],
  ];
  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div className="fs-eyebrow">Stress the plan</div>
      <div className="fs-h2" style={{marginTop:7}}>Fire an adverse scenario at the model and watch the landing move.</div>
      <p style={{fontSize:13,color:"var(--ink-soft)",marginTop:8,maxWidth:760}}>Each preset sets erosion, compression, dispute haircut, cash lag and an execution discount. The headline reads off the live model.</p>
      <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:14}}>
        {Object.entries(presets).map(([k,p])=>(
          <button key={k} className="fs-btn" data-variant={k==="base"?"ghost":"risk"} onClick={()=>applyPreset(p)}>{p.label}</button>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginTop:18,paddingTop:16,borderTop:"1px solid var(--line)"}}>
        <Stat label="Expected landing" value={model.landing.toFixed(2)} unit="B" tone="accent"/>
        <Stat label={model.gap<=0?"Headroom":"Gap to target"} value={Math.abs(model.gap).toFixed(2)} unit="B" tone={model.gap<=0?"good":"risk"}/>
        <Stat label="P(hit target)" value={model.pHit} unit="%" tone={model.pHit>=60?"good":model.pHit>=35?"accent":"risk"}/>
        <Stat label="Year-H cash" value={model.cashLanding.toFixed(2)} unit="B" tone="risk"/>
      </div>
      <div style={{fontSize:11.5,color:"var(--ink-faint)",marginTop:10}}>Current stress — compression {risk.compression}% · haircut {risk.haircut}% · cash lag {risk.cashLag}y · execution discount {risk.execDiscount}%.</div>
    </div>

    <div className="fs-eyebrow" style={{marginBottom:10}}>The critique — and what the model now does about it</div>
    <div style={{display:"grid",gap:8}}>
      {challenges.map(([t,attack,fix])=>(
        <div key={t} className="fs-card" style={{padding:15}}>
          <div className="fs-h3">{t}</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:8}}>
            <div><div className="fs-eyebrow" style={{color:"var(--risk)",marginBottom:4}}>The attack</div><p style={{fontSize:12.5,color:"var(--ink-soft)",margin:0}}>{attack}</p></div>
            <div><div className="fs-eyebrow" style={{color:"var(--good)",marginBottom:4}}>In the model</div><p style={{fontSize:12.5,color:"var(--ink-soft)",margin:0}}>{fix}</p></div>
          </div>
        </div>))}
    </div>
  </div>);
}

/* ---------- Offering generator ---------- */
function GenView({ onAdd }){
  const [pool,setPool]=useState("rnd");
  const [stream,setStream]=useState("Regulatory authoring");
  const [modelKey,setModelKey]=useState("perunit");
  const [rtw,setRtw]=useState("low");
  const [ai,setAi]=useState({loading:false,text:"",error:""});
  const spec=useMemo(()=>buildOffering(pool,stream,modelKey,rtw),[pool,stream,modelKey,rtw]);
  async function enhance(){
    setAi({loading:true,text:"",error:""});
    const prompt=`You are advising ZS Associates on a new pharma services offering. ZS is a cognitive system integrator for regulated life sciences; its wedge is governed decision systems sold as outcomes, though that wedge is contested by IQVIA. Given this offering:
Name: ${spec.name}
Demand pool: ${POOLS[pool].label} (${POOLS[pool].traj})
Value stream: ${stream}
Commercial model: ${MODELS[modelKey].label} — unit: ${MODELS[modelKey].unit}
Target buyer: ${spec.buyer}
ZS right-to-win: ${RTW[rtw].label}
Write three tight sections in plain British English, no preamble, sentence case headers:
VALUE PROPOSITION — 2 sentences on the outcome the client books.
FIRST 90 DAYS — 3 short bullet actions to land a proof point.
WHY ZS WINS — 1-2 sentences on the moat versus IQVIA, Veeva and the big consultancies, and one honest reason it might not.
Keep it under 170 words total.`;
    try{
      const res=await fetch("https://api.anthropic.com/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({model:"claude-sonnet-4-6",max_tokens:1000,messages:[{role:"user",content:prompt}]})});
      const data=await res.json();
      const text=(data.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n").trim();
      if(text) setAi({loading:false,text,error:""}); else setAi({loading:false,text:"",error:"No response came back. The deterministic spec below stands on its own."});
    }catch(e){ setAi({loading:false,text:"",error:"Couldn’t reach the model. The deterministic spec below stands on its own."}); }
  }
  return (<div className="fs-fade" style={{display:"grid",gridTemplateColumns:"300px 1fr",gap:18,alignItems:"start"}}>
    <div className="fs-card" style={{padding:18,position:"sticky",top:150}}>
      <div className="fs-eyebrow" style={{marginBottom:12}}>Configure an offering</div>
      <Field label="Demand pool"><select value={pool} onChange={e=>setPool(e.target.value)}>{Object.entries(POOLS).map(([k,p])=><option key={k} value={k}>{p.label}</option>)}</select></Field>
      <Field label="Value stream"><select value={stream} onChange={e=>setStream(e.target.value)}>{VALUE_STREAMS.map(s=><option key={s} value={s}>{s}</option>)}</select></Field>
      <Field label="Commercial model"><select value={modelKey} onChange={e=>setModelKey(e.target.value)}>{Object.entries(MODELS).map(([k,m])=><option key={k} value={k}>{m.label}</option>)}</select></Field>
      <Field label="ZS right-to-win"><select value={rtw} onChange={e=>setRtw(e.target.value)}>{Object.entries(RTW).map(([k,r])=><option key={k} value={k}>{r.label}</option>)}</select></Field>
      <hr className="fs-rule" style={{margin:"14px 0"}}/>
      <button className="fs-btn" data-variant="accent" style={{width:"100%",marginBottom:8}} onClick={enhance} disabled={ai.loading}>{ai.loading?"Drafting…":"Enhance with AI"}</button>
      <button className="fs-btn" data-variant="ghost" style={{width:"100%"}} onClick={()=>onAdd({ id:`gen-${Date.now()}`, name:spec.name, pool, model:modelKey, size:spec.sizeMid, start:spec.startYear, attain:RTW[rtw].attain, color:spec.color, enabled:true, buyer:spec.buyer, moat:spec.moat, rationale:spec.rationale, moats:deriveMoats(pool,modelKey) })}>Add to simulator →</button>
    </div>
    <div>
      <div className="fs-card" style={{padding:20,marginBottom:14}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:12}}>
          <div><div className="fs-eyebrow">{spec.horizon} · world {spec.world}</div><div className="fs-h2" style={{marginTop:6}}>{spec.name}</div></div>
          <span className="fs-num fs-chip" style={{fontSize:12,padding:"6px 10px"}}>{spec.sizeBand}</span>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:16}}>
          <Detail k="Unit of value" v={spec.unit}/><Detail k="Pricing structure" v={MODELS[modelKey].label}/>
          <Detail k="Target buyer" v={spec.buyer}/><Detail k="Source of moat" v={spec.moat}/>
          <Detail k="Win-probability" v={`${RTW[rtw].attain}% — ${RTW[rtw].label.toLowerCase()} right-to-win`}/><Detail k="Key metrics" v={spec.kpis}/>
          <Detail k="Agent economics" v={spec.agentEcon}/><Detail k="Moat signature" v={spec.moatSig}/>
          <Detail k="Principal risk" v={spec.risk}/>
        </div>
        <div style={{marginTop:14,padding:"12px 14px",background:"var(--surface-2)",borderRadius:9,fontSize:12.5,color:"var(--ink-soft)"}}>{spec.rationale}</div>
      </div>
      {ai.error && <div className="fs-card" style={{padding:14,marginBottom:14,fontSize:12.5,color:"var(--ink-soft)",borderColor:"var(--line-strong)"}}>{ai.error}</div>}
      {ai.text && (<div className="fs-card fs-fade" style={{padding:20}}>
        <div className="fs-eyebrow" style={{marginBottom:8}}>AI-drafted detail · Claude Sonnet</div>
        <div style={{fontSize:13,whiteSpace:"pre-wrap",lineHeight:1.55}}>{ai.text}</div></div>)}
    </div>
  </div>);
}
function Field({ label,children }){ return <div style={{marginBottom:12}}><div style={{fontSize:11.5,color:"var(--ink-soft)",fontWeight:600,marginBottom:5}}>{label}</div>{children}</div>; }
function Detail({ k,v }){ return <div><div className="fs-eyebrow" style={{marginBottom:4}}>{k}</div><div style={{fontSize:13,fontWeight:550}}>{v}</div></div>; }

function buildOffering(pool,stream,modelKey,rtw){
  const m=MODELS[modelKey], poolMeta=POOLS[pool];
  const colorByPool={ ai:"var(--s4)", rnd:"var(--s2)", commercial:"var(--s1)", opmodel:"var(--s3)", governance:"var(--s5)", mna:"var(--s6)" };
  const nameLead={ perunit:"Authoring engine", gainshare:"Outcome programme", hybrid:"Decision system", bot:"Capability build", subusage:"Intelligence platform", assurance:"Assurance service" }[modelKey];
  const name=`${stream} ${nameLead}`;
  const center=+(poolMeta.weight*RTW[rtw].mult*0.9).toFixed(2);
  const lo=Math.max(0.05,+(center*0.7).toFixed(2)), hi=+(center*1.3).toFixed(2), sizeMid=+center.toFixed(2);
  const world=(modelKey==="hybrid"||modelKey==="gainshare"||modelKey==="assurance")?"④":modelKey==="bot"?"③":modelKey==="subusage"?"② / ④":"④";
  const horizon=modelKey==="bot"?"Horizon 1–2":modelKey==="assurance"?"Horizon 3":(pool==="rnd"||pool==="commercial")?"Horizon 2":"Horizon 1–2";
  const buyerByPool={ rnd:"CMO · Head of Regulatory", commercial:"CCO · CDIO", ai:"CDIO · Chief AI Officer", opmodel:"CDIO · COO · GCC lead", governance:"Quality · Regulatory · Chief AI Officer", mna:"CCO · Corporate development" };
  const kpisByModel={ perunit:"Throughput · first-pass acceptance · cost per artifact", gainshare:"Measured lift vs baseline · attribution confidence", hybrid:"Net revenue retention · decisions served · outcome attainment", bot:"Time-to-capability · transfer-to-operate conversion", subusage:"Consumption growth · seat expansion · gross margin on run", assurance:"Certifications issued · audit pass-rate · defects caught pre-submission" };
  const riskByModel={ perunit:"Efficiency cannibalises revenue — price on value, not effort", gainshare:"Attribution disputes — needs the metering layer first", hybrid:"Delivery risk on the balance sheet — fix capital model first", bot:"Transfer leaks the annuity — contract to keep the operate", subusage:"Reseller drift — keep orchestration and metering proprietary", assurance:"Latent demand — sell credibility as a line item, not a footnote" };
  const moatByPool={ rnd:"Governed authoring + regulatory credibility (reSCape lineage)", commercial:"Domain decision truth × ZAIDYN substrate", ai:"Orchestration kept proprietary above the platform", opmodel:"Reference architecture + GxP operating model", governance:"GxP-grade verification — the scarce, defensible asset", mna:"Launch excellence on outcomes" };
  const rtwNote=rtw==="low"?"Deliberate white-space bet — largest pool, but lowest right-to-win; fund with M&A and acqui-hire and expect a long ramp.":rtw==="med"?"Adjacent expansion — partner where the platform owns the data.":"Plays to existing strength — re-price from effort to outcome to defend it.";
  const agentEcon=modelKey==="subusage"?"Own the substrate · rent the model · licence skills":modelKey==="assurance"?"Own the verification IP · licence certification":modelKey==="bot"?"Build to transfer — own the reference architecture":modelKey==="perunit"?"Own the authoring agents · rent the model · meter per artifact":"Rent the intelligence · own the governance · licence the trust";
  const mv=deriveMoats(pool,modelKey);
  const moatSig=Object.entries(mv).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([k])=>MOAT_DIMS[k].label).join(" · ");
  return { name, unit:m.unit, buyer:buyerByPool[pool], moat:moatByPool[pool], kpis:kpisByModel[modelKey], risk:riskByModel[modelKey], agentEcon, moatSig,
    sizeBand:`$${lo}–${hi}B (5-yr, illustrative)`, sizeMid, startYear: modelKey==="bot"||modelKey==="subusage"?1:modelKey==="assurance"?3:2, color:colorByPool[pool], world, horizon, rationale:`${m.note} ${rtwNote}` };
}

/* ---------- Moats ---------- */
function MoatView({ model }){
  const dims=Object.keys(MOAT_DIMS);
  const radarData=dims.map(d=>({dim:MOAT_DIMS[d].short,score:model.prof[d]}));
  const durColor={ "Strongest":"var(--recurring)", "Strong":"var(--good)", "Medium-strong":"var(--s4)", "Contested":"var(--risk)", "Secondary":"var(--ink-faint)" };
  return (<div className="fs-fade">
    <div className="fs-card" style={{padding:20,marginBottom:18}}>
      <div className="fs-eyebrow">The one line</div>
      <div className="fs-h2" style={{marginTop:7,maxWidth:820}}>The moat is the governed, proprietary decision ground-truth you generate by operating regulated decision systems — plus the compliance and trust apparatus that lets you work on data others can’t touch.</div>
      <p style={{fontSize:13,color:"var(--ink-soft)",marginTop:8,maxWidth:760}}>Created by running, not by owning data assets — but only as durable as your ability to keep winning the contest with IQVIA and to aggregate ground-truth across clients. The profile below is size-weighted by your current portfolio.</p>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"320px 1fr",gap:18,marginBottom:22,alignItems:"start"}}>
      <div className="fs-card" style={{padding:16}}>
        <div className="fs-eyebrow" style={{marginBottom:4}}>Portfolio defence profile</div>
        <ResponsiveContainer width="100%" height={230}>
          <RadarChart data={radarData} outerRadius={84}>
            <PolarGrid stroke="var(--line)"/>
            <PolarAngleAxis dataKey="dim" tick={{fontSize:10,fill:"var(--ink-soft)",fontFamily:"var(--mono)"}}/>
            <PolarRadiusAxis domain={[0,3]} tick={false} axisLine={false}/>
            <Radar dataKey="score" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.22} strokeWidth={2}/>
          </RadarChart>
        </ResponsiveContainer>
        <div style={{display:"flex",justifyContent:"space-around",marginTop:6,borderTop:"1px solid var(--line)",paddingTop:12}}>
          <Stat label="Defensibility" value={model.defens} unit="/100" tone={model.defens>=66?"good":"accent"}/>
          <Stat label="Margin · Year H" value={model.marginH} unit="%" tone="good"/>
        </div>
      </div>
      <div style={{display:"grid",gap:8}}>
        {dims.map(d=>(<div key={d} className="fs-card" style={{padding:14}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10}}>
            <span className="fs-h3">{MOAT_DIMS[d].label}</span>
            <span style={{display:"flex",alignItems:"center",gap:8}}>
              <span className="fs-num" style={{fontSize:12,color:"var(--ink-soft)"}}>{model.prof[d].toFixed(1)}/3</span>
              <span className="fs-chip" style={{borderColor:durColor[MOAT_DIMS[d].durability],color:durColor[MOAT_DIMS[d].durability]}}>{MOAT_DIMS[d].durability}</span>
            </span>
          </div>
          <p style={{fontSize:12.5,color:"var(--ink-soft)",margin:"7px 0 0"}}>{MOAT_DIMS[d].pov}</p>
        </div>))}
      </div>
    </div>
    <div className="fs-eyebrow" style={{marginBottom:10}}>Agent economics — rent, own, licence</div>
    <div className="fs-card" style={{padding:6,marginBottom:18}}>
      {AGENT_LAYERS.map((a,i)=>(<div key={a.layer} style={{display:"flex",alignItems:"center",gap:14,padding:"13px 14px",borderTop:i?"1px solid var(--line)":"none"}}>
        <span className="fs-num" style={{width:74,flexShrink:0,fontSize:12,fontWeight:700,color:a.stance==="Own"?"var(--accent-deep)":a.stance==="Licence"?"var(--recurring)":"var(--ink-soft)",textTransform:"uppercase",letterSpacing:"0.06em"}}>{a.stance}</span>
        <div style={{flex:1,minWidth:0}}><div style={{fontSize:13,fontWeight:700}}>{a.layer}</div><div style={{fontSize:12,color:"var(--ink-soft)",marginTop:2}}>{a.note}</div></div>
      </div>))}
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:18}}>
      <div className="fs-card" style={{padding:16}}><div className="fs-h3">Digital workers invert the P&amp;L</div>
        <p style={{fontSize:12.5,color:"var(--ink-soft)",marginTop:7}}>Near-zero marginal cost after build shifts the firm from labour-leverage to fleet and IP-leverage. But early on the build cost and delivery risk make it a margin J-curve — visible in the simulator — not an instant lift.</p></div>
      <div className="fs-card" style={{padding:16}}><div className="fs-h3">The platform you can hold</div>
        <p style={{fontSize:12.5,color:"var(--ink-soft)",marginTop:7}}>The <strong>decision-and-governance orchestration layer</strong> above the systems of record and below the client’s decisions — not a system-of-record or data platform, both already lost to incumbents.</p></div>
    </div>
    <div className="fs-eyebrow" style={{marginBottom:10}}>Dimensions of innovation — the moat lives at their intersection</div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:10}}>
      {[["Technology","Applied and governed, not frontier. Rent the model; differentiate on orchestration, metering and verification."],
        ["Domain understanding","The multiplier. New modalities — GLP-1, radioligand, cell & gene — are fresh learning curves and therefore fresh demand."],
        ["New competencies","Decision architecture, trust and eval engineering, outcome underwriting. Building these is itself the innovation."]].map(([t,d])=>(
        <div key={t} className="fs-card" style={{padding:15}}><div className="fs-h3">{t}</div><p style={{fontSize:12.5,color:"var(--ink-soft)",marginTop:7}}>{d}</p></div>))}
    </div>
  </div>);
}

/* ---------- Commercial models ---------- */
function ModelView(){
  return (<div className="fs-fade">
    <div className="fs-eyebrow" style={{marginBottom:6}}>The commercial continuum</div>
    <p style={{fontSize:13,color:"var(--ink-soft)",maxWidth:740,marginBottom:18}}>How you charge determines what you can build and defend. Hybrid — a predictable base plus an outcome layer — is the winning default; position each offering by how cleanly its value can be metered.</p>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(300px,1fr))",gap:12}}>
      {Object.entries(MODELS).map(([k,m])=>(<div key={k} className="fs-card" style={{padding:16}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
          <span className="fs-h3">{m.label}</span>
          <span className="fs-chip" style={{borderColor:QUALITY_COLORS[m.quality],color:QUALITY_COLORS[m.quality]}}>{QUALITY_LABELS[m.quality]}</span>
        </div>
        <div className="fs-eyebrow" style={{marginBottom:4}}>Unit of value</div>
        <div className="fs-num" style={{fontSize:12.5,marginBottom:8}}>{m.unit}</div>
        <p style={{fontSize:12.5,color:"var(--ink-soft)",margin:0}}>{m.note}</p>
      </div>))}
    </div>
  </div>);
}
