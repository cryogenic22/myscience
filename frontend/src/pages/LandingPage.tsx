import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Database, FlaskConical, Network, Search } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
}

function Counter({ value }: { value: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25 }}
        className="tabular-nums"
      >
        {value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toLocaleString()}
      </motion.span>
    </AnimatePresence>
  );
}

export default function LandingPage({ onEnter, onSearch }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div
      className="min-h-screen overflow-y-auto"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Minimal topbar ── */}
      <header className="sticky top-0 z-40 topbar">
        <div className="flex h-full items-center justify-between px-8">
          <span
            className="font-display text-[17px] font-light tracking-tight"
            style={{ color: 'var(--color-ink)' }}
          >
            {PRODUCT_NAME}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={onSearch}
              className="btn btn-ghost btn-sm flex items-center gap-1.5"
            >
              <Search size={13} />
              Search
            </button>
            <button onClick={onEnter} className="btn btn-primary btn-sm">
              Open
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative flex flex-col items-center justify-center py-32 px-6 text-center overflow-hidden">
        {/* Subtle background gradient */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse 80% 50% at 50% -10%, rgba(28,110,247,0.06) 0%, transparent 70%)',
          }}
        />

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="relative max-w-4xl"
        >
          <p
            className="text-label mb-6"
            style={{ color: 'var(--color-accent)' }}
          >
            Pharmaceutical Intelligence Platform
          </p>

          <h1
            className="text-hero mb-8"
            style={{ color: 'var(--color-ink)' }}
          >
            The intelligence layer
            <br />
            <em>pharma strategy needs</em>
          </h1>

          <p
            className="mx-auto max-w-2xl text-[17px] leading-relaxed mb-12"
            style={{ color: 'var(--color-ink-3)', fontWeight: 300 }}
          >
            A unified knowledge graph across drugs, trials, companies, and literature.
            Evidence-grounded answers for executives and agentic AI workflows.
          </p>

          <div className="flex items-center justify-center gap-4">
            <button
              onClick={onEnter}
              className="btn btn-accent"
              style={{ fontSize: '15px', padding: '13px 28px' }}
            >
              Open Workspace
              <ArrowRight size={16} />
            </button>
            <button
              onClick={onSearch}
              className="btn btn-secondary"
              style={{ fontSize: '15px', padding: '13px 28px' }}
            >
              <Search size={15} />
              Explore
            </button>
          </div>
        </motion.div>
      </section>

      {/* ── Live metrics strip ── */}
      {!stats.loading && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="border-y py-10"
          style={{ borderColor: 'var(--color-line)', background: 'var(--color-surface)' }}
        >
          <div className="mz-container">
            <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
              {[
                { icon: Database, label: 'Total Records', value: stats.totalRecords },
                { icon: Network, label: 'Graph Links', value: stats.entityLinks },
                { icon: FlaskConical, label: 'Clinical Trials', value: stats.trials },
                { icon: Database, label: 'Companies', value: stats.companies },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="text-center">
                  <div
                    className="text-[38px] font-light tracking-tight mb-1"
                    style={{ color: 'var(--color-ink)', fontFamily: 'var(--font-display)' }}
                  >
                    <Counter value={value} />
                  </div>
                  <div style={{ color: 'var(--color-ink-3)', fontSize: '13px' }}>
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.section>
      )}

      {/* ── Pillars ── */}
      <section className="py-28 px-6">
        <div className="mz-container">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="mb-16 text-center"
          >
            <p className="text-label mb-4">Platform</p>
            <h2
              className="font-display text-[36px] font-light tracking-tight"
              style={{ color: 'var(--color-ink)' }}
            >
              Built on connected evidence
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 gap-px sm:grid-cols-2"
            style={{ background: 'var(--color-line)', borderRadius: '20px', overflow: 'hidden' }}
          >
            {[
              {
                n: '01',
                title: 'Ontology Core',
                body: 'Unified entities and typed links across molecules, trials, companies, literature, and market signals.',
              },
              {
                n: '02',
                title: 'GraphRAG Intelligence',
                body: 'Pharma-specific semantics power evidence retrieval and context composition for strategic reasoning.',
              },
              {
                n: '03',
                title: 'Integrated Data Fabric',
                body: 'Continuously ingested evidence from regulatory, clinical, literature, and financial systems.',
              },
              {
                n: '04',
                title: 'Agentic AI Ready',
                body: 'Search, graph, metrics, and query orchestration aligned for autonomous investigative workflows.',
              },
            ].map((pillar, i) => (
              <motion.div
                key={pillar.n}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08, duration: 0.5 }}
                className="group p-10 transition-colors duration-200"
                style={{ background: 'var(--color-surface)' }}
              >
                <div
                  className="text-label mb-6"
                  style={{ color: 'var(--color-ink-4)' }}
                >
                  {pillar.n}
                </div>
                <h3
                  className="text-[20px] font-medium tracking-tight mb-3"
                  style={{ color: 'var(--color-ink)' }}
                >
                  {pillar.title}
                </h3>
                <p
                  className="text-[14px] leading-relaxed"
                  style={{ color: 'var(--color-ink-3)', fontWeight: 300 }}
                >
                  {pillar.body}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Sources ── */}
      <section
        className="py-16 text-center"
        style={{ color: 'var(--color-ink-4)', fontSize: '12px', letterSpacing: '0.05em' }}
      >
        ClinicalTrials.gov · PubMed · FDA Orange Book · SEC Edgar · ChEMBL · Open Targets
      </section>
    </div>
  );
}
