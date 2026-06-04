import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight, ArrowUpRight, Radio, Layers, Swords, Stamp,
  ShieldCheck, Bot, Network, FileCheck2,
} from 'lucide-react';
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import '../styles/landing.css';

/**
 * Landing page — value-forward, ground-up.
 *
 * Built on a dedicated stylesheet (styles/landing.css) of semantic classes +
 * design tokens, NOT Tailwind utilities — utilities generate on demand and can
 * differ between local and Railway builds, which is what made an earlier
 * utility-heavy version render fine locally yet collapse (left-aligned, default
 * fonts) in production. Plain CSS classes are deterministic everywhere.
 *
 * The story mirrors the actual product loop: Sense → Synthesize → War-game →
 * Decide, every claim grounded in a cited fact. Metrics are honest counts from
 * /health (no fabricated figures).
 */

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
  onCI?: () => void;
}

const EASE = [0.16, 1, 0.3, 1] as const;

function Counter({ value }: { value: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.2 }}
        className="tabular-nums"
      >
        {value >= 1_000_000
          ? `${(value / 1_000_000).toFixed(1)}M`
          : value >= 1000
            ? `${(value / 1000).toFixed(1)}k`
            : value.toLocaleString()}
      </motion.span>
    </AnimatePresence>
  );
}

// Real ingestion connectors — honest, not aspirational logos.
const SOURCES = [
  'ClinicalTrials.gov', 'PubMed', 'FDA openFDA', 'SEC EDGAR',
  'DailyMed (SPL)', 'Orange Book', 'Purple Book', 'EMA',
];

const SPINE = [
  {
    icon: Radio, kicker: 'Sense',
    title: 'Always-on evidence sensing',
    body: 'Continuously ingests clinical, regulatory, and commercial evidence across public sources, resolves it to one entity graph, and flags what changed — so a competitor’s readout never slips past you.',
  },
  {
    icon: Layers, kicker: 'Synthesize',
    title: 'A living dossier per asset',
    body: 'Every drug becomes a structured dossier answering the eight questions strategy actually asks — indications, competitors, clinical, positioning, sales, pricing, access — each line traceable to its source.',
  },
  {
    icon: Swords, kicker: 'War-game',
    title: 'Game-theoretic scenarios',
    body: 'Derive event-triggered scenarios and play them out — guided, game-theoretic, or against an autonomous adversary — to see the robust move before the market forces your hand.',
  },
  {
    icon: Stamp, kicker: 'Decide',
    title: 'Decisions you can defend',
    body: 'Produce signed decision briefs where every quantitative claim cites a fact in the ledger. No hallucinated figures — if it isn’t grounded, it doesn’t ship.',
  },
];

const DIFFERENTIATORS = [
  {
    icon: ShieldCheck, title: 'Grounded by construction',
    body: 'Every output ties to exact source passages with a confidence and a fact class. Numbers that don’t trace to evidence are stripped before you ever see them.',
  },
  {
    icon: Bot, title: 'Three agents, always on',
    body: 'Sentinel senses, Strategist frames and simulates, Curator learns from outcomes — and you can nudge any of them when judgement is needed.',
  },
  {
    icon: Network, title: 'A graph, not a feed',
    body: 'Drugs, trials, companies, mechanisms, and literature link into one traversable graph, so context compounds instead of scattering across tabs.',
  },
  {
    icon: FileCheck2, title: 'Auditable end to end',
    body: 'From raw signal to signed decision, the provenance chain is immutable and replayable — the audit trail a regulated strategy team needs.',
  },
];

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
            <span className="lp-brand__sub">{PRODUCT_SUBTITLE}</span>
          </div>
          <div className="lp-header__actions">
            <ThemeToggle />
            <button className="lp-btn lp-btn--text lp-btn--sm" onClick={onSearch}>Data catalog</button>
            <button className="lp-btn lp-btn--dark lp-btn--sm" onClick={onCI}>
              Launch cockpit <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="lp-hero">
        <div className="lp-wrap">
          <motion.div
            className="lp-hero__inner"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
          >
            <span className="lp-eyebrow">Evidence-grounded · Agentic · Auditable</span>
            <h1 className="lp-hero__title">
              Pharma strategy,<br />
              <em>grounded in evidence.</em>
            </h1>
            <p className="lp-hero__subtitle">
              {PRODUCT_NAME} senses clinical, regulatory, and commercial evidence in real time,
              assembles it into living asset dossiers, war-games competitive moves, and produces
              decisions where <strong>every claim cites its source.</strong>
            </p>
            <div className="lp-actions">
              <button className="lp-btn lp-btn--primary lp-btn--lg" onClick={onCI}>
                Launch CI Cockpit <ArrowRight size={18} />
              </button>
              <button className="lp-btn lp-btn--ghost lp-btn--lg" onClick={onEnter}>
                Enter workspace
              </button>
            </div>
            {!stats.loading && (
              <motion.p
                className="lp-trustline"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 0.6 }}
              >
                Grounded in {stats.connectors || SOURCES.length} live sources ·{' '}
                {stats.totalRecords.toLocaleString()} evidence records
              </motion.p>
            )}
          </motion.div>
        </div>
      </section>

      {/* ── Source coverage strip ── */}
      <div className="lp-band">
        <div className="lp-wrap--wide lp-sources">
          <span className="lp-sources__label">Continuously sensing across</span>
          <div className="lp-sources__list">
            {SOURCES.map((s) => <span key={s} className="lp-sources__item">{s}</span>)}
          </div>
        </div>
      </div>

      {/* ── The spine ── */}
      <section className="lp-section">
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">The closed loop</div>
            <h2 className="lp-section__title">From signal to decision, without losing the thread.</h2>
          </div>
          <div className="lp-grid">
            {SPINE.map((step, i) => {
              const Icon = step.icon;
              return (
                <motion.div
                  key={step.kicker}
                  className="lp-card"
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: i * 0.08, duration: 0.5, ease: EASE }}
                >
                  <div className="lp-step__row">
                    <span className="lp-card__icon"><Icon size={20} /></span>
                    <span className="lp-card__kicker">{String(i + 1).padStart(2, '0')} · {step.kicker}</span>
                  </div>
                  <h3 className="lp-card__title lp-step__title">{step.title}</h3>
                  <p className="lp-card__body">{step.body}</p>
                </motion.div>
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

      {/* ── Differentiators ── */}
      <section className="lp-section">
        <div className="lp-wrap">
          <div className="lp-section__head">
            <div className="lp-kicker">Why it’s different</div>
            <h2 className="lp-section__title">Built for decisions you have to stand behind.</h2>
          </div>
          <div className="lp-grid">
            {DIFFERENTIATORS.map((d, i) => {
              const Icon = d.icon;
              return (
                <motion.div
                  key={d.title}
                  className="lp-card lp-diff"
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: i * 0.08, duration: 0.5, ease: EASE }}
                >
                  <span className="lp-card__icon" style={{ flexShrink: 0 }}><Icon size={22} /></span>
                  <div>
                    <h3 className="lp-card__title lp-diff__title">{d.title}</h3>
                    <p className="lp-card__body">{d.body}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Closing CTA ── */}
      <section className="lp-cta">
        <div className="lp-wrap">
          <motion.div
            className="lp-cta__panel"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, ease: EASE }}
          >
            <h2 className="lp-cta__title">See it on a real asset.</h2>
            <p className="lp-cta__body">
              Open the cockpit and walk a live engagement — dossier, scenarios, war-game,
              and a decision brief, all grounded in cited evidence.
            </p>
            <div className="lp-cta__actions">
              <button className="lp-btn lp-btn--primary lp-btn--lg" onClick={onCI}>
                Launch CI Cockpit <ArrowRight size={18} />
              </button>
              <button className="lp-btn lp-btn--text lp-btn--lg" onClick={onSearch}>
                Browse the data catalog <ArrowUpRight size={17} />
              </button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="lp-footer">
        <div className="lp-wrap--wide lp-footer__inner">
          <span className="lp-footer__name">{PRODUCT_NAME}</span>
          <span className="lp-footer__meta">{PRODUCT_SUBTITLE} · Confidential</span>
        </div>
      </footer>
    </div>
  );
}
