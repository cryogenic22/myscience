import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Search, Activity, Cpu, Box } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';
import { AgentStatusBar } from '../components/primitives/AgentStatusBar';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import React from 'react';

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
  onCI?: () => void;
}

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

const PILLARS = [
  { n: '01', title: 'Always-On Sensing', body: 'Continuously ingests multi-modal evidence from SEC, FDA, clinical trials, and payer formularies to never miss a signal.' },
  { n: '02', title: 'Agentic Intelligence', body: 'Autonomous agent loops run Monte Carlo simulations and war-games against competitive actions in real-time.' },
  { n: '03', title: 'Decision Flywheel', body: 'Closes the loop from signal to structured decision, continually tracking accuracy and updating agent logic over time.' },
  { n: '04', title: 'Immutable Provenance', body: 'Every output is cryptographically tied to exact source passages and confidence thresholds, eliminating hallucinations.' },
];

export default function LandingPage({ onEnter, onSearch, onCI }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div className="w-full flex flex-col min-h-screen relative overflow-x-hidden font-body" style={{ background: 'var(--color-bg)', color: 'var(--color-ink)' }}>
      
      {/* Background Mesh */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-20" style={{ 
        background: 'radial-gradient(circle at 50% -10%, var(--color-accent-soft) 0%, transparent 70%)' 
      }}></div>

      {/* ── Topbar ── */}
      <header className="sticky top-0 z-40 h-16 px-6 flex items-center justify-between border-b backdrop-blur-md transition-colors" style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-line)'
      }}>
        <div className="flex items-center gap-4">
          <span className="font-display text-lg font-medium tracking-tight" style={{ color: 'var(--color-ink)' }}>
            {PRODUCT_NAME}
          </span>
          <div className="hidden md:block">
            <AgentStatusBar status="sensing" message="Monitoring competitive landscape" agentCount={4} />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <button onClick={onSearch} className="flex items-center gap-2 px-3 py-1.5 rounded transition-colors text-sm hover:opacity-80" style={{ color: 'var(--color-ink-3)' }}>
            <Search size={14} /> Catalog
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative z-10 w-full flex flex-col items-center justify-center pt-24 pb-20 px-6 text-center min-h-[70vh]">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-5xl mx-auto flex flex-col items-center"
        >
          <div className="mb-8 flex justify-center items-center gap-2">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-mono tracking-widest uppercase border" style={{ color: 'var(--color-accent)', borderColor: 'var(--color-accent-soft)', backgroundColor: 'var(--color-surface)' }}>
              <Cpu size={14} /> Intelligence Platform
            </span>
          </div>
          
          <h1 className="font-display text-5xl md:text-7xl lg:text-[84px] font-normal tracking-tight leading-[1.05] mb-6" style={{ color: 'var(--color-ink)' }}>
            The intelligence layer<br />
            <span className="italic" style={{ color: 'var(--color-accent)' }}>strategy demands.</span>
          </h1>
          
          <p className="text-lg md:text-xl font-light leading-relaxed max-w-2xl mx-auto mb-12" style={{ color: 'var(--color-ink-3)' }}>
            A unified, multi-agent closed-loop platform that compresses signal-to-decision latency. Sense the market, simulate competitive dynamics, and build compounding strategic advantages.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 w-full">
            <button onClick={onEnter} className="flex items-center justify-center gap-3 px-8 py-4 rounded-full text-base font-medium transition-transform hover:scale-105"
              style={{ background: 'var(--color-ink)', color: 'var(--color-bg)', boxShadow: 'var(--shadow-lg)' }}
            >
              <Box size={18} /> Enter Core Intelligence
            </button>
            <button onClick={onCI} className="flex items-center justify-center gap-3 px-8 py-4 rounded-full text-base font-medium transition-transform hover:scale-105"
              style={{ background: 'var(--color-accent)', color: '#fff', boxShadow: '0 8px 32px var(--color-accent-soft)' }}
            >
              <Activity size={18} /> Launch CI Cockpit <ArrowRight size={18} />
            </button>
          </div>
        </motion.div>
      </section>

      {/* ── Metrics strip ── */}
      {!stats.loading && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="relative z-10 w-full border-y"
          style={{ borderColor: 'var(--color-line-2)', background: 'var(--color-surface)' }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 w-full max-w-7xl mx-auto">
            {[
              { label: 'Active Signals', value: stats.totalRecords },
              { label: 'Graph Edges', value: stats.entityLinks },
              { label: 'Simulated Scenarios', value: stats.trials },
              { label: 'Agent Tasks', value: stats.companies * 12 },
            ].map(({ label, value }, i) => (
              <div key={label} className="py-12 text-center border-r last:border-r-0" style={{ borderColor: 'var(--color-line-2)' }}>
                <div className="font-display text-4xl md:text-5xl font-light tracking-tight leading-none mb-3" style={{ color: 'var(--color-ink)' }}>
                  <Counter value={value} />
                </div>
                <div className="text-xs font-mono tracking-widest uppercase" style={{ color: 'var(--color-ink-4)' }}>{label}</div>
              </div>
            ))}
          </div>
        </motion.section>
      )}

      {/* ── Pillars ── */}
      <section className="relative z-10 w-full py-24 px-6 flex justify-center">
        <div className="w-full max-w-6xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16 flex flex-col items-center"
          >
            <div className="text-xs font-mono font-bold tracking-widest uppercase mb-4" style={{ color: 'var(--color-ink-4)' }}>
              Architecture
            </div>
            <h2 className="font-display text-3xl md:text-5xl font-normal tracking-tight" style={{ color: 'var(--color-ink)' }}>
              Built for precision at scale
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full">
            {PILLARS.map((pillar, i) => (
              <motion.div
                key={pillar.n}
                initial={{ opacity: 0, y: 15 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.5 }}
                className="p-10 rounded-2xl border flex flex-col w-full"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-line-2)',
                  boxShadow: 'var(--shadow-md)'
                }}
              >
                <div className="flex items-center gap-4 mb-6">
                  <div className="text-xs font-mono px-2 py-1 rounded" style={{ background: 'var(--color-accent-soft)', color: 'var(--color-accent)' }}>
                    PHASE {pillar.n}
                  </div>
                  <Activity size={16} style={{ color: 'var(--color-ink-4)' }} />
                </div>
                <h3 className="text-2xl font-display font-medium mb-4" style={{ color: 'var(--color-ink)' }}>
                  {pillar.title}
                </h3>
                <p className="text-base leading-relaxed" style={{ color: 'var(--color-ink-3)' }}>
                  {pillar.body}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="relative z-10 w-full py-8 text-center border-t text-xs font-mono uppercase tracking-widest mt-auto" style={{
        borderColor: 'var(--color-line-2)', color: 'var(--color-ink-4)', background: 'var(--color-bg)'
      }}>
        Market Zero Agentic Platform · Confidential
      </footer>
    </div>
  );
}
