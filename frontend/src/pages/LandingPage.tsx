import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight, ArrowUpRight, Radio, Layers, Swords, Stamp,
  ShieldCheck, Bot, Network, FileCheck2,
} from 'lucide-react';
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';
import { ThemeToggle } from '../components/primitives/ThemeToggle';

/**
 * Landing page — ground-up refresh.
 *
 * Tells the real story of the product instead of generic platform copy: a
 * closed loop from evidence to defensible decision (Sense → Synthesize →
 * War-game → Decide), every claim grounded in a cited fact. Generous vertical
 * rhythm and full-bleed bands (no cramped max-w-2xl columns); separation via
 * tone-shift + shadow only (D2 border discipline — no border utilities).
 * Metrics are honest: real counts from /health, no fabricated figures.
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

// The product's actual evidence sources (connectors). Honest — these are the
// live ingestion connectors, not aspirational logos.
const SOURCES = [
  'ClinicalTrials.gov', 'PubMed', 'FDA openFDA', 'SEC EDGAR',
  'DailyMed (SPL)', 'Orange Book', 'Purple Book', 'EMA',
];

// The closed loop — what the platform actually does, in order.
const SPINE = [
  {
    icon: Radio,
    kicker: 'Sense',
    title: 'Always-on evidence sensing',
    body: 'Continuously ingests clinical, regulatory, and commercial evidence across public sources, resolves it to a single entity graph, and flags what changed — so a competitor’s readout never slips past you.',
  },
  {
    icon: Layers,
    kicker: 'Synthesize',
    title: 'A living dossier per asset',
    body: 'Every drug becomes a structured dossier answering the eight questions strategy actually asks — indications, competitors, clinical, positioning, sales, pricing, access — each line traceable to its source.',
  },
  {
    icon: Swords,
    kicker: 'War-game',
    title: 'Game-theoretic scenarios',
    body: 'Derive event-triggered scenarios and play them out — guided, game-theoretic, or against an autonomous adversary — to see the robust move before the market forces your hand.',
  },
  {
    icon: Stamp,
    kicker: 'Decide',
    title: 'Decisions you can defend',
    body: 'Produce signed decision briefs where every quantitative claim cites a fact in the ledger. No hallucinated figures — if it isn’t grounded, it doesn’t ship.',
  },
];

const DIFFERENTIATORS = [
  {
    icon: ShieldCheck,
    title: 'Grounded by construction',
    body: 'Every output is tied to exact source passages with a confidence and a fact class. Numbers that don’t trace to evidence are stripped before you ever see them.',
  },
  {
    icon: Bot,
    title: 'Three agents, always on',
    body: 'Sentinel senses, Strategist frames and simulates, Curator learns from outcomes — and you can nudge any of them when judgement is needed.',
  },
  {
    icon: Network,
    title: 'A graph, not a feed',
    body: 'Drugs, trials, companies, mechanisms, and literature are linked into one traversable graph, so context compounds instead of scattering across tabs.',
  },
  {
    icon: FileCheck2,
    title: 'Auditable end to end',
    body: 'From raw signal to signed decision, the provenance chain is immutable and replayable — the audit trail a regulated strategy team needs.',
  },
];

export default function LandingPage({ onEnter, onSearch, onCI }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div
      className="w-full flex flex-col relative overflow-x-hidden font-body"
      // Global `body { overflow:hidden }` (right for the cockpit, which scrolls
      // its own panes) would otherwise clip this tall page at the fold. The
      // landing owns its scroll: fill #root and scroll internally.
      style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', background: 'var(--color-bg)', color: 'var(--color-ink)' }}
    >
      {/* Ambient mesh */}
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(900px circle at 50% -20%, var(--color-accent-soft) 0%, transparent 60%)',
        }}
      />

      {/* ── Header ── */}
      <header
        className="sticky top-0 z-40 backdrop-blur-md transition-colors"
        style={{ backgroundColor: 'color-mix(in srgb, var(--color-surface) 82%, transparent)' }}
      >
        <div className="w-full max-w-7xl mx-auto h-16 px-6 md:px-10 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-xl font-medium tracking-tight" style={{ color: 'var(--color-ink)' }}>
              {PRODUCT_NAME}
            </span>
            <span
              className="hidden sm:inline font-mono uppercase tracking-widest"
              style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}
            >
              {PRODUCT_SUBTITLE}
            </span>
          </div>
          <div className="flex items-center gap-2 md:gap-4">
            <ThemeToggle />
            <button
              onClick={onSearch}
              className="hidden sm:inline-flex px-3 py-2 rounded-full transition-opacity hover:opacity-70"
              style={{ color: 'var(--color-ink-2)', fontSize: 'var(--text-base)' }}
            >
              Data catalog
            </button>
            <button
              onClick={onCI}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full transition-transform hover:scale-[1.03]"
              style={{ background: 'var(--color-ink)', color: 'var(--color-bg)', fontSize: 'var(--text-base)', boxShadow: 'var(--shadow-sm)' }}
            >
              Launch cockpit <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative z-10 w-full px-6 md:px-10">
        <div className="w-full max-w-5xl mx-auto pt-28 md:pt-36 pb-20 md:pb-28 flex flex-col items-center text-center">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE }}
            className="flex flex-col items-center"
          >
            <span
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full font-mono uppercase tracking-widest mb-8"
              style={{ color: 'var(--color-accent)', background: 'var(--color-accent-soft)', fontSize: 'var(--text-xs)' }}
            >
              Evidence-grounded · Agentic · Auditable
            </span>

            <h1 className="font-display font-normal tracking-tight" style={{ color: 'var(--color-ink)', fontSize: 'var(--text-hero)', lineHeight: 1.04 }}>
              Pharma strategy,
              <br />
              <span className="italic" style={{ color: 'var(--color-accent)' }}>grounded in evidence.</span>
            </h1>

            <p
              className="font-light max-w-3xl mt-8"
              style={{ color: 'var(--color-ink-2)', fontSize: 'clamp(17px, 2vw, 22px)', lineHeight: 1.55 }}
            >
              {PRODUCT_NAME} senses clinical, regulatory, and commercial evidence in real time,
              assembles it into living asset dossiers, war-games competitive moves, and produces
              decisions where <span style={{ color: 'var(--color-ink)' }}>every claim cites its source.</span>
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-12">
              <button
                onClick={onCI}
                className="inline-flex items-center justify-center gap-2.5 px-7 py-3.5 rounded-full font-medium transition-transform hover:scale-[1.03]"
                style={{ background: 'var(--color-accent)', color: '#fff', fontSize: 'var(--text-md-2)', boxShadow: 'var(--shadow-md)' }}
              >
                Launch CI Cockpit <ArrowRight size={18} />
              </button>
              <button
                onClick={onEnter}
                className="inline-flex items-center justify-center gap-2.5 px-7 py-3.5 rounded-full font-medium transition-transform hover:scale-[1.03]"
                style={{ background: 'var(--color-surface)', color: 'var(--color-ink)', fontSize: 'var(--text-md-2)', boxShadow: 'var(--shadow-sm)' }}
              >
                Enter workspace
              </button>
            </div>

            {!stats.loading && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4, duration: 0.6 }}
                className="font-mono uppercase tracking-widest mt-10"
                style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}
              >
                Grounded in {stats.connectors || SOURCES.length} live sources ·{' '}
                {stats.totalRecords.toLocaleString()} evidence records
              </motion.p>
            )}
          </motion.div>
        </div>
      </section>

      {/* ── Source coverage strip ── */}
      <section className="relative z-10 w-full" style={{ background: 'var(--color-surface-2)' }}>
        <div className="w-full max-w-7xl mx-auto px-6 md:px-10 py-10 flex flex-col items-center gap-6">
          <span className="font-mono uppercase tracking-widest" style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}>
            Continuously sensing across
          </span>
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
            {SOURCES.map((s) => (
              <span key={s} className="font-display" style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-lg)' }}>
                {s}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── The spine: Sense → Synthesize → War-game → Decide ── */}
      <section className="relative z-10 w-full px-6 md:px-10">
        <div className="w-full max-w-6xl mx-auto py-24 md:py-32">
          <div className="max-w-2xl mb-16">
            <div className="font-mono uppercase tracking-widest mb-4" style={{ color: 'var(--color-accent)', fontSize: 'var(--text-xs)' }}>
              The closed loop
            </div>
            <h2 className="font-display font-normal tracking-tight" style={{ color: 'var(--color-ink)', fontSize: 'clamp(30px, 4vw, 48px)', lineHeight: 1.1 }}>
              From signal to decision, without losing the thread.
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {SPINE.map((step, i) => {
              const Icon = step.icon;
              return (
                <motion.div
                  key={step.kicker}
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: i * 0.08, duration: 0.5, ease: EASE }}
                  className="p-8 md:p-10 rounded-2xl"
                  style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-sm)' }}
                >
                  <div className="flex items-center gap-3 mb-6">
                    <span
                      className="inline-flex items-center justify-center rounded-xl"
                      style={{ width: 40, height: 40, background: 'var(--color-accent-soft)', color: 'var(--color-accent)' }}
                    >
                      <Icon size={20} />
                    </span>
                    <span className="font-mono uppercase tracking-widest" style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}>
                      {String(i + 1).padStart(2, '0')} · {step.kicker}
                    </span>
                  </div>
                  <h3 className="font-display font-medium mb-3" style={{ color: 'var(--color-ink)', fontSize: 'var(--text-xl-2)' }}>
                    {step.title}
                  </h3>
                  <p style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-md-2)', lineHeight: 1.6 }}>
                    {step.body}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Live metrics (honest counts from /health) ── */}
      {!stats.loading && (
        <section className="relative z-10 w-full" style={{ background: 'var(--color-surface-2)' }}>
          <div className="w-full max-w-7xl mx-auto px-6 md:px-10 py-16 md:py-20">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-y-12 gap-x-6">
              {[
                { label: 'Drugs tracked', value: stats.drugs },
                { label: 'Clinical trials', value: stats.trials },
                { label: 'Publications', value: stats.articles },
                { label: 'Graph edges', value: stats.entityLinks },
              ].map(({ label, value }) => (
                <div key={label} className="text-center">
                  <div className="font-display font-light tracking-tight leading-none mb-3" style={{ color: 'var(--color-ink)', fontSize: 'clamp(34px, 4.5vw, 52px)' }}>
                    <Counter value={value} />
                  </div>
                  <div className="font-mono uppercase tracking-widest" style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}>
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Why teams trust it ── */}
      <section className="relative z-10 w-full px-6 md:px-10">
        <div className="w-full max-w-6xl mx-auto py-24 md:py-32">
          <div className="max-w-2xl mb-16">
            <div className="font-mono uppercase tracking-widest mb-4" style={{ color: 'var(--color-accent)', fontSize: 'var(--text-xs)' }}>
              Why it’s different
            </div>
            <h2 className="font-display font-normal tracking-tight" style={{ color: 'var(--color-ink)', fontSize: 'clamp(30px, 4vw, 48px)', lineHeight: 1.1 }}>
              Built for decisions you have to stand behind.
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {DIFFERENTIATORS.map((d, i) => {
              const Icon = d.icon;
              return (
                <motion.div
                  key={d.title}
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: i * 0.08, duration: 0.5, ease: EASE }}
                  className="flex gap-5 p-8 rounded-2xl"
                  style={{ background: 'var(--color-surface)', boxShadow: 'var(--shadow-sm)' }}
                >
                  <span
                    className="inline-flex items-center justify-center rounded-xl shrink-0"
                    style={{ width: 44, height: 44, background: 'var(--color-accent-soft)', color: 'var(--color-accent)' }}
                  >
                    <Icon size={22} />
                  </span>
                  <div>
                    <h3 className="font-display font-medium mb-2" style={{ color: 'var(--color-ink)', fontSize: 'var(--text-xl)' }}>
                      {d.title}
                    </h3>
                    <p style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-md)', lineHeight: 1.6 }}>
                      {d.body}
                    </p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Closing CTA band ── */}
      <section className="relative z-10 w-full px-6 md:px-10 pb-24 md:pb-32">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EASE }}
          className="w-full max-w-6xl mx-auto rounded-3xl px-8 md:px-16 py-16 md:py-20 text-center"
          style={{ background: 'var(--color-ink)', boxShadow: 'var(--shadow-lg)' }}
        >
          <h2 className="font-display font-normal tracking-tight mx-auto max-w-3xl" style={{ color: 'var(--color-bg)', fontSize: 'clamp(28px, 4vw, 46px)', lineHeight: 1.1 }}>
            See it on a real asset.
          </h2>
          <p className="mx-auto max-w-xl mt-5" style={{ color: 'color-mix(in srgb, var(--color-bg) 70%, transparent)', fontSize: 'var(--text-md-2)', lineHeight: 1.6 }}>
            Open the cockpit and walk a live engagement — dossier, scenarios, war-game,
            and a decision brief, all grounded in cited evidence.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
            <button
              onClick={onCI}
              className="inline-flex items-center justify-center gap-2.5 px-7 py-3.5 rounded-full font-medium transition-transform hover:scale-[1.03]"
              style={{ background: 'var(--color-accent)', color: '#fff', fontSize: 'var(--text-md-2)', boxShadow: 'var(--shadow-md)' }}
            >
              Launch CI Cockpit <ArrowRight size={18} />
            </button>
            <button
              onClick={onSearch}
              className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-full font-medium transition-opacity hover:opacity-80"
              style={{ background: 'transparent', color: 'var(--color-bg)', fontSize: 'var(--text-md-2)' }}
            >
              Browse the data catalog <ArrowUpRight size={17} />
            </button>
          </div>
        </motion.div>
      </section>

      {/* ── Footer ── */}
      <footer
        className="relative z-10 w-full py-8 px-6 md:px-10 mt-auto"
        style={{ background: 'var(--color-bg)' }}
      >
        <div className="w-full max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="font-display" style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-base)' }}>
            {PRODUCT_NAME}
          </span>
          <span className="font-mono uppercase tracking-widest" style={{ color: 'var(--color-ink-4)', fontSize: 'var(--text-xs)' }}>
            {PRODUCT_SUBTITLE} · Confidential
          </span>
        </div>
      </footer>
    </div>
  );
}
