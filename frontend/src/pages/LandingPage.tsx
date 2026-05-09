import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Search, Activity, Cpu } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';
import { AgentStatusBar } from '../components/primitives/AgentStatusBar';
import React from 'react';

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
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

export default function LandingPage({ onEnter, onSearch }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div style={{ minHeight: '100vh', overflowY: 'auto', background: 'var(--color-bg)', fontFamily: 'var(--font-body)', position: 'relative' }}>
      
      {/* Background Mesh */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-20" style={{ 
        background: 'radial-gradient(circle at 50% 0%, var(--color-accent-soft) 0%, transparent 60%)' 
      }}></div>

      {/* ── Topbar ── */}
      <header className="relative z-40 sticky top-0 h-[52px] flex items-center justify-between px-8 border-b" style={{
        background: 'rgba(13, 17, 23, 0.85)', backdropFilter: 'saturate(180%) blur(20px)',
        borderColor: 'var(--color-line)'
      }}>
        <div className="flex items-center gap-4">
          <span style={{ fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 500, color: 'var(--color-ink)', letterSpacing: '-0.02em' }}>
            {PRODUCT_NAME}
          </span>
          <div className="hidden md:block">
            <AgentStatusBar status="sensing" message="Monitoring competitive landscape" agentCount={4} />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={onSearch} className="flex items-center gap-2 px-3 py-1.5 rounded transition-colors text-sm" style={{ color: 'var(--color-ink-3)' }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--color-ink)'; e.currentTarget.style.backgroundColor = 'var(--color-surface-2)'; }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--color-ink-3)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            <Search size={14} /> Catalog
          </button>
          <button onClick={onEnter} className="flex items-center gap-2 px-4 py-1.5 rounded-full transition-all text-sm font-medium" style={{ background: 'var(--color-ink)', color: 'var(--color-bg)' }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.05)'; }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
          >
            Launch Cockpit <ArrowRight size={14} />
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative z-10 pt-32 pb-24 px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-4xl mx-auto"
        >
          <div className="mb-6 flex justify-center items-center gap-2">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-mono tracking-widest uppercase border" style={{ color: 'var(--color-accent)', borderColor: 'var(--color-accent-soft)', backgroundColor: 'var(--color-surface)' }}>
              <Cpu size={12} /> Autonomous CI
            </span>
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(48px, 6vw, 84px)', fontWeight: 400, lineHeight: 1.05, letterSpacing: '-0.03em', color: 'var(--color-ink)', marginBottom: '24px' }}>
            The intelligence layer<br />
            <span style={{ color: 'var(--color-accent)', fontStyle: 'italic' }}>strategy demands.</span>
          </h1>
          <p style={{ fontSize: '18px', lineHeight: 1.6, color: 'var(--color-ink-3)', fontWeight: 300, maxWidth: '600px', margin: '0 auto 48px' }}>
            A unified, multi-agent closed-loop platform that compresses signal-to-decision latency. Sense the market, simulate competitive dynamics, and build compounding strategic advantages.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button onClick={onEnter} className="flex items-center gap-2 px-8 py-4 rounded-full text-base font-medium transition-all shadow-lg hover:shadow-xl cursor-pointer"
              style={{ background: 'var(--color-accent)', color: '#fff', boxShadow: '0 8px 32px rgba(88, 166, 255, 0.2)' }}
            >
              Enter Decision Flywheel <ArrowRight size={16} />
            </button>
            <button onClick={onSearch} className="flex items-center gap-2 px-8 py-4 rounded-full text-base font-medium transition-colors border cursor-pointer"
              style={{ background: 'var(--color-surface)', borderColor: 'var(--color-line-2)', color: 'var(--color-ink)' }}
            >
              <Search size={16} /> Query Graph
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
          className="relative z-10 border-y"
          style={{ borderColor: 'var(--color-line-2)', background: 'var(--color-surface)' }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 max-w-5xl mx-auto">
            {[
              { label: 'Active Signals', value: stats.totalRecords },
              { label: 'Graph Edges', value: stats.entityLinks },
              { label: 'Simulated Scenarios', value: stats.trials },
              { label: 'Agent Tasks', value: stats.companies * 12 },
            ].map(({ label, value }, i) => (
              <div key={label} className="py-10 text-center" style={{ borderRight: i % 4 !== 3 ? '1px solid var(--color-line-2)' : 'none' }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: '42px', fontWeight: 300, letterSpacing: '-0.02em', color: 'var(--color-ink)', lineHeight: 1, marginBottom: '12px' }}>
                  <Counter value={value} />
                </div>
                <div className="text-[10px] font-mono tracking-widest uppercase" style={{ color: 'var(--color-ink-4)' }}>{label}</div>
              </div>
            ))}
          </div>
        </motion.section>
      )}

      {/* ── Pillars ── */}
      <section className="relative z-10 py-24 px-8">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <div className="text-[11px] font-mono font-bold tracking-widest uppercase mb-4" style={{ color: 'var(--color-ink-4)' }}>
              Architecture
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px, 4vw, 48px)', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--color-ink)' }}>
              Built for precision at scale
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {PILLARS.map((pillar, i) => (
              <motion.div
                key={pillar.n}
                initial={{ opacity: 0, y: 15 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.5 }}
                className="p-10 rounded-2xl border flex flex-col"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-line-2)',
                  boxShadow: '0 4px 24px rgba(0,0,0,0.2)'
                }}
              >
                <div className="flex items-center gap-4 mb-6">
                  <div className="text-[10px] font-mono px-2 py-1 rounded" style={{ background: 'var(--color-accent-soft)', color: 'var(--color-accent)' }}>
                    PHASE {pillar.n}
                  </div>
                  <Activity size={16} style={{ color: 'var(--color-ink-4)' }} />
                </div>
                <h3 className="text-xl font-medium mb-3" style={{ color: 'var(--color-ink)', fontFamily: 'var(--font-display)' }}>
                  {pillar.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--color-ink-3)' }}>
                  {pillar.body}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="relative z-10 py-8 text-center border-t text-[11px] font-mono uppercase tracking-widest" style={{
        borderColor: 'var(--color-line-2)', color: 'var(--color-ink-4)'
      }}>
        Market Zero Agentic Platform · Confidential
      </footer>
    </div>
  );
}
