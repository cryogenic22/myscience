import type { ComponentType } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  Bot,
  Building2,
  Database,
  FlaskConical,
  GitBranch,
  Network,
  Search,
  Sparkles,
  Zap,
} from 'lucide-react';
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
}

function LiveNumber({ value }: { value: number }) {
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
        {value.toLocaleString()}
      </motion.span>
    </AnimatePresence>
  );
}

export default function LandingPage({ onEnter, onSearch }: LandingPageProps) {
  const stats = useHealthStats();

  const domainEntities = stats.drugs + stats.trials + stats.articles + stats.companies + stats.events;
  const ontologyDensity = domainEntities > 0 ? (stats.entityLinks / domainEntities) : 0;

  return (
    <div className="min-h-screen overflow-y-auto bg-surface">
      <div className="mx-auto max-w-5xl px-6 pb-32 pt-16 sm:px-10 lg:pt-24">

        {/* ── Hero ── */}
        <section className="text-center">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand/12 to-brand/4 ring-1 ring-brand/10">
              <Zap size={28} className="text-brand" />
            </div>

            <h1 className="text-[42px] font-bold tracking-tight text-ink sm:text-[54px] lg:text-[64px]">
              {PRODUCT_NAME}
            </h1>
            <p className="mt-2 text-[17px] text-ink-soft sm:text-[19px]">
              {PRODUCT_SUBTITLE}
            </p>

            <p className="mx-auto mt-6 max-w-2xl text-[15px] leading-relaxed text-ink-soft/80">
              A connected domain graph unifying therapeutic signals, trial evidence,
              company strategy, and literature provenance. Built for executive trust
              and agentic AI workflows.
            </p>

            <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={onEnter}
                className="btn-primary group inline-flex items-center gap-2 rounded-xl px-7 py-3.5 text-[14px] font-semibold shadow-lg shadow-brand/20 transition-all hover:shadow-xl hover:shadow-brand/30"
              >
                Open Workspace
                <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
              </button>
              <button
                onClick={onSearch}
                className="btn-secondary inline-flex items-center gap-2 rounded-xl px-7 py-3.5 text-[14px] font-semibold"
              >
                <Search size={15} />
                Explore Search
              </button>
            </div>
          </motion.div>
        </section>

        {/* ── Live Stats ── */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-20"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Records" value={stats.totalRecords} icon={Database} />
            <StatTile label="Graph Links" value={stats.entityLinks} icon={Network} />
            <StatTile label="Clinical Trials" value={stats.trials} icon={FlaskConical} />
            <StatTile label="Companies" value={stats.companies} icon={Building2} />
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            {stats.services.map((service) => (
              <span key={service} className="rounded-full bg-white px-3 py-1 text-[11px] font-medium text-ink-soft shadow-sm">
                {service}
              </span>
            ))}
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-medium text-emerald-700">
              {stats.services.length} services online
            </span>
          </div>
        </motion.section>

        {/* ── Pillars ── */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-20"
        >
          <h2 className="text-center text-[11px] font-semibold uppercase tracking-[0.2em] text-ink-soft">
            Platform Architecture
          </h2>
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <PillarCard
              icon={Network}
              title="Ontology Core"
              detail="Unified entities and typed links across molecules, trials, companies, literature, and market signals."
              stat={`${stats.entityLinks.toLocaleString()} connected links`}
            />
            <PillarCard
              icon={GitBranch}
              title="Domain Semantics"
              detail="Pharma-specific semantics power retrieval and context composition for strategic and clinical reasoning."
              stat={`${ontologyDensity.toFixed(1)} links per entity`}
            />
            <PillarCard
              icon={Database}
              title="Integrated Data Fabric"
              detail="Continuously ingested evidence from regulatory, clinical, literature, and financial systems."
              stat={`${stats.connectors.toLocaleString()} active source channels`}
            />
            <PillarCard
              icon={Bot}
              title="Agentic AI Ready"
              detail="Search, graph, metrics, and query orchestration aligned for autonomous investigative workflows."
              stat={`${stats.services.length} services online`}
            />
          </div>
        </motion.section>

        {/* ── Footer attribution ── */}
        <div className="mt-24 text-center text-[11px] tracking-wide text-ink-soft/50">
          Grounded in ClinicalTrials.gov · PubMed · FDA Orange Book · SEC Edgar
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function StatTile({ label, value, icon: Icon }: { label: string; value: number; icon: ComponentType<{ size?: number; className?: string }> }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm text-center">
      <Icon size={16} className="mx-auto mb-2 text-ink-soft/50" />
      <div className="text-[28px] font-bold tracking-tight text-ink">
        <LiveNumber value={value} />
      </div>
      <div className="mt-0.5 text-[12px] text-ink-soft">{label}</div>
    </div>
  );
}

function PillarCard({ icon: Icon, title, detail, stat }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  title: string;
  detail: string;
  stat: string;
}) {
  return (
    <div className="group rounded-2xl bg-white p-6 shadow-sm transition-all hover:shadow-md">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 text-ink-soft transition-colors group-hover:bg-brand/8 group-hover:text-brand">
        <Icon size={18} />
      </div>
      <h3 className="text-[16px] font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{detail}</p>
      <p className="mt-3 text-[12px] font-medium text-brand">{stat}</p>
    </div>
  );
}
