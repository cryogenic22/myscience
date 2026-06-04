import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight, ArrowUpRight, Bot, Infinity as InfinityIcon, ShieldCheck,
  Database, Sparkles, Network, Crosshair, Radio, Swords, Zap, RefreshCw,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import { AGENTS, type AgentId } from '../components/primitives/AgentGlyph';
import '../styles/landing.css';

/**
 * Landing microsite — value-forward, ground-up.
 *
 * Two themes: (1) pharma's edge is buried in fragmented, mostly-unstructured
 * evidence that's impossible to curate by hand — we make it AI-ready with
 * agentic AI; (2) on top of that we run an intelligence SUBSTRATE that drives
 * the SDAL decision flywheel (Sense → Decide → Act → Learn) for competitive
 * intelligence and war-gaming. AI-led, not AI-assist. 24×7 autonomous. Beta.
 *
 * Built on an authored stylesheet (styles/landing.css) of semantic classes +
 * design tokens — never Tailwind utilities (which under-generate on Railway).
 * Metrics from /health are honest counts; business-impact figures are labelled
 * industry estimates, not our results.
 */

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
  onCI?: () => void;
}

const EASE = [0.16, 1, 0.3, 1] as const;

function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ delay, duration: 0.5, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

function Counter({ value }: { value: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span key={value} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }} className="tabular-nums">
        {value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M` : value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toLocaleString()}
      </motion.span>
    </AnimatePresence>
  );
}

// Public evidence connected today; licensed/internal sources flow via the
// connector framework + document upload.
const SOURCES_LIVE = ['ClinicalTrials.gov', 'PubMed', 'FDA openFDA', 'SEC EDGAR', 'DailyMed (SPL)', 'Orange Book', 'Purple Book', 'EMA'];
const SOURCES_CONNECT = ['IQVIA', 'Veeva CRM', 'MMIT payer', 'Evaluate', 'Earnings decks', 'CSRs & 10-Ks'];

const SHIFT = [
  { icon: Bot, title: 'AI-led, not AI-assist', body: 'Not a copilot you prompt. Autonomous agents own the loop — they sense, reason, and propose the move; you set the corridors and approve.' },
  { icon: InfinityIcon, title: '24×7 curation & stewardship', body: 'Evidence is ingested, resolved, and quality-stewarded around the clock — so the knowledge store is current the moment a decision is needed, not after the next quarterly review.' },
  { icon: ShieldCheck, title: 'Grounded by construction', body: 'Every assertion cites the exact source fact, with a confidence and a class. Numbers that don’t trace to evidence are stripped before they reach a decision.' },
];

// The substrate, bottom-up. DOM order is bottom→top; CSS column-reverse renders
// Intelligence on top ("what sits on top").
const STACK = [
  { icon: Database, tier: 'Layer 1 · Collect', title: 'Every source, structured and not', body: 'Continuous ingestion across public, licensed, and internal evidence — filings, trials, labels, literature, congress decks, payer policy, patents. Most of it unstructured.' },
  { icon: Sparkles, tier: 'Layer 2 · Make AI-ready', title: 'Curate the noise into facts', body: 'Semantic enrichment, entity resolution, and LLM extraction turn raw documents into typed, evidence-bearing facts. The fact is the atom — the unit everything else is built from.' },
  { icon: Network, tier: 'Layer 3 · The substrate', title: 'One knowledge store, many lenses', body: 'Facts and entities form a traversable graph. A signal is a scored, timed lens over those facts — not a parallel store. Every new document deepens the whole substrate at once.' },
  { icon: Crosshair, tier: 'Layer 4 · Intelligence', title: 'Decisions sit on top', body: 'Living dossiers, scenarios, war-games, and signed decision briefs read the substrate directly — so the intelligence compounds as the evidence grows.', top: true },
];

const FACT_CLASSES = [
  { k: 'ref', label: 'Reference' }, { k: 'corp', label: 'Corporate' }, { k: 'signal', label: 'Signal' },
  { k: 'inferred', label: 'Inferred' }, { k: 'internal', label: 'Internal' },
];

const FLYWHEEL = [
  { icon: Radio, step: 'Sense', title: 'Continuous competitive sensing', body: 'Watch approvals and filings, trial registrations and readouts, Rx-share trajectories, formulary moves, pricing, patent and litigation events, congress signals — classified and threat-scored as they land.' },
  { icon: Swords, step: 'Decide / Simulate', title: 'War-game the response', body: 'Model erosion curves from analogues, simulate scenarios and game-theoretic counter-moves, and surface the robust play — with a defensible ROI before anyone commits.' },
  { icon: Zap, step: 'Act', title: 'Activate the playbook', body: 'Turn the chosen move into a pre-designed response playbook and orchestrate it cross-functionally — compressing time-to-response from weeks to days, inside set decision corridors.' },
  { icon: RefreshCw, step: 'Learn', title: 'Track, calibrate, compound', body: 'Track share retention and playbook effectiveness, tune signal sensitivity, and grow the analogue library — so every competitive event makes the next response sharper.' },
];

const IMPACT = [
  { num: '3–8', unit: ' share pts', label: 'lost in the first 12 months when a competitive threat is detected late.' },
  { num: '15–25%', label: 'more market share retained by brands that respond within 2 weeks of a signal vs. quarterly cadences.' },
  { num: '8–12 wks → <2', label: 'time-to-response when pre-designed playbooks activate on signal instead of after review.' },
];

const AGENT_COPY: Record<AgentId, string> = {
  sentinel: 'Senses — sweeps every source around the clock, resolves entities, scores and routes what matters now.',
  strategist: 'Frames and simulates — derives scenarios, war-games competitive moves, and drafts the grounded recommendation.',
  curator: 'Learns — stewards data quality, tracks outcomes, and recalibrates the system from what actually happened.',
};

export default function LandingPage({ onEnter, onSearch, onCI }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div className="lp-root">
      <div className="lp-mesh" aria-hidden="true" />

      {/* ── Header ── */}
      <header className="lp-header">
        <div className="lp-wrap--wide lp-header__inner" style={{ marginInline: 'auto' }}>
          <div className="lp-brand">
            <span className="lp-brand__name">{PRODUCT_NAME}</span>
            <span className="lp-beta"><span className="lp-beta__dot" />Beta</span>
          </div>
          <div className="lp-header__actions">
            <ThemeToggle />
            <button className="lp-btn lp-btn--text lp-btn--sm" onClick={onSearch}>Data catalog</button>
            <button className="lp-btn lp-btn--dark lp-btn--sm" onClick={onCI}>Launch cockpit <ArrowRight size={15} /></button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="lp-hero">
        <div className="lp-wrap">
          <motion.div className="lp-hero__inner" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EASE }}>
            <span className="lp-eyebrow">AI-led · Autonomous · 24×7</span>
            <h1 className="lp-hero__title">
              The intelligence substrate<br />
              <em>for pharma decisions.</em>
            </h1>
            <p className="lp-hero__subtitle">
              Your edge is buried in fragmented, mostly-unstructured evidence. {PRODUCT_NAME} makes that
              evidence <strong>AI-ready</strong> with agentic AI, then runs an intelligence substrate that
              drives the <strong>Sense → Decide → Act → Learn</strong> flywheel for competitive intelligence
              and war-gaming. AI-led, not AI-assist.
            </p>
            <div className="lp-actions">
              <button className="lp-btn lp-btn--primary lp-btn--lg" onClick={onCI}>Launch CI Cockpit <ArrowRight size={18} /></button>
              <button className="lp-btn lp-btn--ghost lp-btn--lg" onClick={onEnter}>Enter workspace</button>
            </div>
            {!stats.loading && (
              <motion.p className="lp-trustline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 0.6 }}>
                Grounded in {stats.connectors || SOURCES_LIVE.length} live sources · {stats.totalRecords.toLocaleString()} evidence records
              </motion.p>
            )}
          </motion.div>
        </div>
      </section>

      {/* ── Problem ── */}
      <section className="lp-section" style={{ paddingBlock: '88px' }}>
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">The problem</div>
            <h2 className="lp-section__title">Rich insight. Impossible to curate by hand.</h2>
          </div>
          <Reveal>
            <div className="lp-problem">
              <p className="lp-problem__lead">
                A competitor’s edge shows up first in a 200-page filing, a congress poster, a formulary
                footnote, an earnings aside — <em>not</em> in a tidy table. The signal is real and the
                window is short, but the volume and the unstructured mess make it impossible to curate at
                the cadence decisions actually need. So teams fall back to quarterly reviews — and lose the
                first move.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── The shift ── */}
      <section className="lp-section" style={{ paddingTop: 0 }}>
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">The shift</div>
            <h2 className="lp-section__title">A system that decides, not just assists.</h2>
          </div>
          <div className="lp-grid">
            {SHIFT.map((s, i) => {
              const Icon = s.icon;
              return (
                <Reveal key={s.title} delay={i * 0.08} className="lp-card">
                  <div className="lp-step__row">
                    <span className="lp-card__icon"><Icon size={20} /></span>
                  </div>
                  <h3 className="lp-card__title lp-step__title">{s.title}</h3>
                  <p className="lp-card__body">{s.body}</p>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── The stack ── */}
      <div className="lp-band">
        <section className="lp-section">
          <div className="lp-wrap">
            <div className="lp-section__head">
              <div className="lp-kicker">How it works</div>
              <h2 className="lp-section__title">From raw evidence to decisions — one substrate.</h2>
              <p className="lp-section__lead">Four layers. The fact is the atom; the graph is the substrate; signals are lenses over it; intelligence sits on top and compounds as evidence grows.</p>
            </div>
            <div className="lp-stack">
              {STACK.map((l) => {
                const Icon = l.icon;
                return (
                  <div key={l.tier} className={`lp-layer${l.top ? ' lp-layer--top' : ''}`}>
                    <div className="lp-layer__head">
                      <span className="lp-card__icon"><Icon size={20} /></span>
                      <span className="lp-layer__tier">{l.tier}</span>
                      <h3 className="lp-layer__title">{l.title}</h3>
                    </div>
                    <div>
                      <p className="lp-layer__body">{l.body}</p>
                      {l.tier.includes('Collect') && (
                        <p className="lp-layer__meta">
                          Live: {SOURCES_LIVE.join(' · ')}<br />Connects to: {SOURCES_CONNECT.join(' · ')}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* the atom — fact-class system */}
            <div className="lp-fc-row" aria-label="Fact classes">
              {FACT_CLASSES.map((fc) => (
                <span key={fc.k} className="lp-fc"><span className={`lp-fc__dot lp-fc__dot--${fc.k}`} />{fc.label}</span>
              ))}
            </div>
          </div>
        </section>
      </div>

      {/* ── SDAL flywheel ── */}
      <section className="lp-section">
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">The decision flywheel</div>
            <h2 className="lp-section__title">Sense → Decide → Act → Learn, on autopilot.</h2>
            <p className="lp-section__lead">The substrate powers a closed loop for competitive intelligence and war-gaming — each turn faster and sharper than the last.</p>
          </div>
          <div className="lp-flywheel">
            {FLYWHEEL.map((p, i) => {
              const Icon = p.icon;
              return (
                <Reveal key={p.step} delay={i * 0.07} className="lp-phase">
                  <div className="lp-step__row">
                    <span className="lp-card__icon"><Icon size={20} /></span>
                    <span className="lp-phase__step">{String(i + 1).padStart(2, '0')} · {p.step}</span>
                  </div>
                  <h3 className="lp-phase__title">{p.title}</h3>
                  <p className="lp-phase__body">{p.body}</p>
                </Reveal>
              );
            })}
          </div>
          <div className="lp-flywheel__note"><RefreshCw size={14} /> Continuous — Learn feeds the next Sense.</div>
        </div>
      </section>

      {/* ── Business impact (industry estimates) ── */}
      <div className="lp-band">
        <section className="lp-section">
          <div className="lp-wrap">
            <div className="lp-section__head">
              <div className="lp-kicker">Why speed wins</div>
              <h2 className="lp-section__title">The cost of finding out late.</h2>
            </div>
            <div className="lp-impact">
              {IMPACT.map((s, i) => (
                <Reveal key={i} delay={i * 0.08} className="lp-impact__stat">
                  <div className="lp-impact__num"><em>{s.num}</em>{s.unit || ''}</div>
                  <div className="lp-impact__label">{s.label}</div>
                </Reveal>
              ))}
            </div>
            <p className="lp-impact__src">Industry estimates for mid-size specialty brands — illustrative of the decision window, not platform results.</p>
          </div>
        </section>
      </div>

      {/* ── Agents ── */}
      <section className="lp-section">
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">The team behind the loop</div>
            <h2 className="lp-section__title">Three autonomous agents, always on.</h2>
          </div>
          <div className="lp-agents">
            {(['sentinel', 'strategist', 'curator'] as AgentId[]).map((id, i) => {
              const a = AGENTS[id];
              return (
                <Reveal key={id} delay={i * 0.08} className="lp-agent">
                  <h3 className="lp-agent__name">
                    <span className="lp-agent__glyph" style={{ background: `rgba(${a.rgb}, 0.16)`, color: `rgb(${a.rgb})` }}>{a.glyph}</span>
                    {a.name}
                  </h3>
                  <div className="lp-agent__role">{a.role}</div>
                  <p className="lp-agent__body">{AGENT_COPY[id]}</p>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Live metrics (honest /health counts) ── */}
      {!stats.loading && (
        <div className="lp-band">
          <div className="lp-wrap--wide lp-metrics">
            {[
              { label: 'Drugs tracked', value: stats.drugs },
              { label: 'Clinical trials', value: stats.trials },
              { label: 'Publications', value: stats.articles },
              { label: 'Graph edges', value: stats.entityLinks },
            ].map(({ label, value }) => (
              <div key={label} className="lp-metric">
                <div className="lp-metric__value"><Counter value={value} /></div>
                <div className="lp-metric__label">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Closing CTA ── */}
      <section className="lp-cta">
        <div className="lp-wrap">
          <Reveal className="lp-cta__panel">
            <span className="lp-beta" style={{ marginBottom: 20 }}><span className="lp-beta__dot" />Beta</span>
            <h2 className="lp-cta__title">See the substrate on a real asset.</h2>
            <p className="lp-cta__body">Open the cockpit and walk a live engagement — evidence, dossier, war-game, and a grounded decision brief. This is an early Beta; the intelligence deepens with every source you add.</p>
            <div className="lp-cta__actions">
              <button className="lp-btn lp-btn--primary lp-btn--lg" onClick={onCI}>Launch CI Cockpit <ArrowRight size={18} /></button>
              <button className="lp-btn lp-btn--text lp-btn--lg" onClick={onSearch}>Browse the data catalog <ArrowUpRight size={17} /></button>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="lp-footer">
        <div className="lp-wrap--wide lp-footer__inner">
          <span className="lp-footer__name">{PRODUCT_NAME}</span>
          <span className="lp-footer__meta">{PRODUCT_SUBTITLE} · Beta · Confidential</span>
        </div>
      </footer>
    </div>
  );
}
