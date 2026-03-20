import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Search } from 'lucide-react';
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
  { n: '01', title: 'Ontology Core', body: 'Unified entities and typed links across molecules, trials, companies, literature, and market signals.' },
  { n: '02', title: 'GraphRAG Intelligence', body: 'Pharma-specific semantics power evidence retrieval and context composition for strategic reasoning.' },
  { n: '03', title: 'Integrated Data Fabric', body: 'Continuously ingested evidence from regulatory, clinical, literature, and financial systems.' },
  { n: '04', title: 'Agentic AI Ready', body: 'Search, graph, metrics, and query orchestration aligned for autonomous investigative workflows.' },
];

export default function LandingPage({ onEnter, onSearch }: LandingPageProps) {
  const stats = useHealthStats();

  return (
    <div style={{ minHeight: '100vh', overflowY: 'auto', background: 'var(--color-bg)', fontFamily: 'var(--font-body)' }}>

      {/* ── Topbar ── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 40, height: '52px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 40px',
        background: 'rgba(250,250,248,0.92)', backdropFilter: 'saturate(180%) blur(20px)',
        WebkitBackdropFilter: 'saturate(180%) blur(20px)', borderBottom: '1px solid var(--color-line)',
      }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '16px', fontWeight: 400, color: 'var(--color-ink)', letterSpacing: '-0.01em' }}>
          {PRODUCT_NAME}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button onClick={onSearch} style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '6px 12px',
            borderRadius: '7px', background: 'transparent', border: 'none', cursor: 'pointer',
            fontSize: '13px', color: 'var(--color-ink-3)', fontFamily: 'var(--font-body)', transition: 'background 140ms, color 140ms',
          }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-surface-2)'; e.currentTarget.style.color = 'var(--color-ink)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--color-ink-3)'; }}
          >
            <Search size={13} /> Search
          </button>
          <button onClick={onEnter} style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '6px 15px',
            borderRadius: '980px', background: 'var(--color-ink)', border: 'none', cursor: 'pointer',
            fontSize: '13px', fontWeight: 500, color: '#fff', fontFamily: 'var(--font-body)', transition: 'background 140ms',
          }}
            onMouseEnter={e => (e.currentTarget.style.background = '#2c2c30')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-ink)')}
          >
            Open <ArrowRight size={12} />
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section style={{ position: 'relative', padding: '88px 24px 72px', textAlign: 'center', overflow: 'hidden' }}>
        <div aria-hidden style={{ pointerEvents: 'none', position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 60% 40% at 50% -5%, rgba(28,110,247,0.07) 0%, transparent 65%)' }} />
        <motion.div
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
          style={{ position: 'relative', maxWidth: '820px', margin: '0 auto' }}
        >
          <div style={{ marginBottom: '24px', fontSize: '11px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-accent)' }}>
            Pharmaceutical Intelligence Platform
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(44px, 5.5vw, 72px)', fontWeight: 300, lineHeight: 1.09, letterSpacing: '-0.025em', color: 'var(--color-ink)', marginBottom: '24px' }}>
            The intelligence layer<br /><em>pharma strategy needs</em>
          </h1>
          <p style={{ fontSize: '16px', lineHeight: 1.7, color: 'var(--color-ink-3)', fontWeight: 300, maxWidth: '500px', margin: '0 auto 36px' }}>
            A unified knowledge graph across drugs, trials, companies, and literature. Evidence-grounded answers for executives and agentic AI workflows.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
            <button onClick={onEnter} style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '12px 24px',
              borderRadius: '980px', background: 'var(--color-accent)', border: 'none', cursor: 'pointer',
              fontSize: '15px', fontWeight: 500, color: '#fff', fontFamily: 'var(--font-body)',
              boxShadow: '0 4px 12px rgba(28,110,247,0.26)', transition: 'all 160ms',
            }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-accent-dark)'; e.currentTarget.style.boxShadow = '0 6px 18px rgba(28,110,247,0.36)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--color-accent)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(28,110,247,0.26)'; }}
            >
              Open Workspace <ArrowRight size={15} />
            </button>
            <button onClick={onSearch} style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '12px 24px',
              borderRadius: '980px', background: 'var(--color-surface)', border: '1px solid var(--color-line)',
              cursor: 'pointer', fontSize: '15px', fontWeight: 500, color: 'var(--color-ink)',
              fontFamily: 'var(--font-body)', transition: 'all 160ms',
            }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface-2)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-surface)')}
            >
              <Search size={14} /> Explore
            </button>
          </div>
        </motion.div>
      </section>

      {/* ── Metrics strip ── */}
      {!stats.loading && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          style={{ borderTop: '1px solid var(--color-line)', borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', maxWidth: '880px', margin: '0 auto' }}>
            {[
              { label: 'Total Records', value: stats.totalRecords },
              { label: 'Graph Links', value: stats.entityLinks },
              { label: 'Clinical Trials', value: stats.trials },
              { label: 'Companies', value: stats.companies },
            ].map(({ label, value }, i) => (
              <div key={label} style={{
                padding: '36px 20px', textAlign: 'center',
                borderRight: i < 3 ? '1px solid var(--color-line)' : 'none',
              }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: '38px', fontWeight: 300, letterSpacing: '-0.025em', color: 'var(--color-ink)', lineHeight: 1, marginBottom: '8px' }}>
                  <Counter value={value} />
                </div>
                <div style={{ fontSize: '12px', color: 'var(--color-ink-4)', letterSpacing: '0.01em' }}>{label}</div>
              </div>
            ))}
          </div>
        </motion.section>
      )}

      {/* ── Pillars ── */}
      <section style={{ padding: '88px 40px 80px' }}>
        <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            style={{ textAlign: 'center', marginBottom: '56px' }}
          >
            <div style={{ marginBottom: '14px', fontSize: '11px', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--color-ink-4)' }}>
              Platform
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px, 2.8vw, 38px)', fontWeight: 300, letterSpacing: '-0.02em', color: 'var(--color-ink)', lineHeight: 1.15 }}>
              Built on connected evidence
            </h2>
          </motion.div>

          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1px',
            background: 'var(--color-line)', border: '1px solid var(--color-line)',
            borderRadius: '18px', overflow: 'hidden',
          }}>
            {PILLARS.map((pillar, i) => (
              <motion.div
                key={pillar.n}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.06, duration: 0.45 }}
                style={{
                  background: 'var(--color-surface)',
                  padding: '40px 40px 44px',
                  minHeight: '190px',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 600, letterSpacing: '0.1em', color: 'var(--color-ink-4)', marginBottom: '18px' }}>
                  {pillar.n}
                </div>
                <h3 style={{ fontSize: '18px', fontWeight: 600, letterSpacing: '-0.015em', color: 'var(--color-ink)', marginBottom: '10px', lineHeight: 1.3 }}>
                  {pillar.title}
                </h3>
                <p style={{ fontSize: '14px', lineHeight: 1.65, color: 'var(--color-ink-3)', fontWeight: 300, flexGrow: 1 }}>
                  {pillar.body}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer style={{
        padding: '28px 40px', textAlign: 'center', borderTop: '1px solid var(--color-line)',
        fontSize: '12px', letterSpacing: '0.04em', color: 'var(--color-ink-4)',
      }}>
        Grounded in ClinicalTrials.gov · PubMed · FDA Orange Book · SEC Edgar · ChEMBL · Open Targets
      </footer>
    </div>
  );
}
