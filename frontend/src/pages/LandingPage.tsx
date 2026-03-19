import type { ComponentType } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  Bot,
  Building2,
  Database,
  FlaskConical,
  GitBranch,
  Network,
  Search,
  Sparkles,
  Workflow,
} from 'lucide-react';
import type { SourceCoverageItem } from '../api';
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from '../brand';
import { useHealthStats } from '../hooks/useHealthStats';

interface LandingPageProps {
  onEnter: () => void;
  onSearch: () => void;
}

const FALLBACK_SOURCES = [
  'openfda',
  'clinicaltrials_gov',
  'pubmed',
  'sec_edgar',
  'fda_shortages',
  'openpayments',
];

function formatSourceName(source: string): string {
  return source
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatTimestamp(value: string | null): string {
  if (!value) return 'just now';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function sourceTotalRecords(source: SourceCoverageItem): number {
  const explicitTotal = Number(source.total_records);
  if (Number.isFinite(explicitTotal) && explicitTotal >= 0) return explicitTotal;
  const fallback = Number(source.records);
  return Number.isFinite(fallback) ? fallback : 0;
}

function sourceLastPullRecords(source: SourceCoverageItem): number | null {
  const value = Number(source.last_pull_records);
  if (!Number.isFinite(value) || value < 0) return null;
  return value;
}

function LiveNumber({ value }: { value: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
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
  const sourceCoverage = stats.sourceCoverage.length > 0
    ? stats.sourceCoverage
    : FALLBACK_SOURCES.map((source) => ({ source, records: 0, last_retrieved: null }));
  const topSources = sourceCoverage.slice(0, 6);
  const maxSourceRecords = Math.max(...topSources.map((item) => sourceTotalRecords(item)), 1);

  const pillars: Array<{
    title: string;
    detail: string;
    stat: string;
    icon: ComponentType<{ size?: number; className?: string }>;
  }> = [
    {
      title: 'Ontology Core',
      detail: 'Unified entities and typed links across molecules, trials, companies, literature, and market signals.',
      stat: `${stats.entityLinks.toLocaleString()} connected links`,
      icon: Network,
    },
    {
      title: 'Domain Semantics',
      detail: 'Pharma-specific semantics power retrieval and context composition for strategic and clinical reasoning.',
      stat: `${ontologyDensity.toFixed(1)} links per entity`,
      icon: GitBranch,
    },
    {
      title: 'Integrated Data Fabric',
      detail: 'Continuously ingested evidence from regulatory, clinical, literature, and financial systems.',
      stat: `${stats.connectors.toLocaleString()} active source channels`,
      icon: Database,
    },
    {
      title: 'Agentic AI Ready',
      detail: 'Search, graph, metrics, and query orchestration are aligned for autonomous investigative workflows.',
      stat: `${stats.services.length.toLocaleString()} services online`,
      icon: Bot,
    },
  ];

  return (
    <div className="workspace-canvas min-h-screen overflow-y-auto">
      <div className="shell-center px-8 pb-28 pt-12 lg:px-10">
        <header className="mx-auto mb-14 flex w-full max-w-6xl flex-wrap items-end justify-between gap-6">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Product Overview</p>
            <h1 className="mt-2 text-[34px] font-semibold tracking-tight text-slate-900">{PRODUCT_NAME}</h1>
            <p className="mt-1 text-[15px] text-slate-500">{PRODUCT_SUBTITLE}</p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white/80 px-3 py-1.5 text-xs text-slate-600">
            <Activity size={12} className="pulse-live" />
            Live metrics every 30 seconds
          </div>
        </header>

        <section className="hero-light relative overflow-visible rounded-lg border border-slate-200/80 px-8 py-12 sm:px-11 sm:py-14">
          <div className="pointer-events-none absolute inset-0 hero-grid opacity-50" />
          <div className="relative grid grid-cols-1 items-start gap-10 xl:grid-cols-[1.15fr_0.85fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white/85 px-3.5 py-1.5 text-xs font-medium text-slate-700">
                <Sparkles size={12} />
                Pharma standard for connected intelligence
              </div>

              <h2 className="mt-7 max-w-[17ch] text-[clamp(2.65rem,5.2vw,4.85rem)] font-semibold leading-[1.02] tracking-tight text-slate-900">
                Ontology intelligence for
                <span className="block text-slate-500">agentic pharma systems.</span>
              </h2>
              <p className="mt-6 max-w-3xl text-[17px] leading-relaxed text-slate-600">
                Build on a connected domain graph that unifies therapeutic signals, trial evidence, company strategy,
                and literature provenance. The experience is designed for executive trust, scientific rigor, and AI-ready operations.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-3">
                <button
                  onClick={onEnter}
                  className="btn-primary inline-flex items-center gap-2 rounded-md px-6 py-3 text-sm font-semibold transition-colors"
                >
                  Enter Core Workspace
                  <ArrowRight size={15} />
                </button>
                <button
                  onClick={onSearch}
                  className="btn-secondary inline-flex items-center gap-2 rounded-md border border-slate-200 px-6 py-3 text-sm font-semibold transition-colors"
                >
                  Explore Search
                  <Search size={15} />
                </button>
              </div>

              <div className="mt-8 flex flex-wrap gap-3 text-[12px] text-slate-600">
                <span className="chip-plain inline-flex max-w-[16rem] items-center overflow-hidden text-ellipsis whitespace-nowrap">
                  Top company: {stats.topCompany || 'N/A'}
                </span>
                <span className="chip-plain inline-flex max-w-[18rem] items-center overflow-hidden text-ellipsis whitespace-nowrap">
                  Top pipeline signal: {stats.topDrug || 'N/A'}
                </span>
                <span className="chip-plain inline-flex">
                  Last sync {formatTimestamp(stats.refreshedAt)}
                </span>
              </div>
            </div>

            <div className="glass-dark rounded-lg border border-slate-200/80 p-6">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold text-slate-800">Platform Pulse</h3>
                <span className="text-[11px] text-slate-500">Live</span>
              </div>

              <div className="grid grid-cols-2 gap-3.5">
                <PulseTile icon={Database} label="Records" value={stats.totalRecords} />
                <PulseTile icon={Network} label="Graph Links" value={stats.entityLinks} />
                <PulseTile icon={FlaskConical} label="Trial Rows" value={stats.trials} />
                <PulseTile icon={Building2} label="Companies" value={stats.companies} />
              </div>

              <div className="mt-5 rounded-md border border-slate-200 bg-white p-4">
                <div className="text-[11px] text-slate-500">Operational services</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {stats.services.map((service) => (
                    <span key={service} className="rounded-sm border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600">
                      {service}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section-space">
          <div className="mx-auto max-w-6xl">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Product Pillars</h3>
            <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-slate-600">
              Structured for ontology-first reasoning, connected evidence, and reliable automation across domain workflows.
            </p>
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:gap-5">
              {pillars.map((pillar) => {
                const Icon = pillar.icon;
                return (
                  <div key={pillar.title} className="card-hover rounded-lg border border-slate-200/80 bg-white/78 px-5 py-5">
                    <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700">
                      <Icon size={16} />
                    </div>
                    <div className="text-[16px] font-semibold text-slate-900">{pillar.title}</div>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">{pillar.detail}</p>
                    <div className="mt-3 text-[12px] font-medium text-brand-dark">{pillar.stat}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="section-space">
          <div className="card mx-auto max-w-6xl p-6">
            <div className="mb-5 flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Connected Source Fabric</h3>
              <span className="text-xs text-slate-500">{topSources.length} channels</span>
            </div>
            <p className="mb-3 text-[12px] text-slate-500">
              Source bars show total indexed records. Last pull counts are shown when provided by the pipeline.
            </p>
            <div className="space-y-3">
              {topSources.map((source) => {
                const totalRecords = sourceTotalRecords(source);
                const lastPullRecords = sourceLastPullRecords(source);
                const widthPct = Math.round((totalRecords / maxSourceRecords) * 100);
                return (
                  <div key={source.source} className="rounded-md border border-slate-200/80 bg-white/76 px-4 py-3">
                    <div className="mb-2 flex items-center justify-between text-xs">
                      <span className="max-w-[13rem] truncate font-medium text-slate-700">{formatSourceName(source.source)}</span>
                      <span className="shrink-0 text-slate-500">
                        <LiveNumber value={totalRecords} /> total
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <motion.div
                        key={`${source.source}-${totalRecords}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.max(widthPct, totalRecords > 0 ? 4 : 0)}%` }}
                        transition={{ duration: 0.35 }}
                        className="h-full bg-slate-800"
                      />
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-3 text-[11px] text-slate-500">
                      <span>Last retrieved {formatTimestamp(source.last_retrieved ?? null)}</span>
                      <span className="shrink-0">
                        {lastPullRecords !== null ? `Last pull ${lastPullRecords.toLocaleString()}` : 'Last pull n/a'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
            {stats.error && (
              <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                Live metrics degraded: {stats.error}
              </div>
            )}
          </div>
        </section>

        <section className="section-space">
          <div className="mx-auto max-w-4xl text-center">
            <div className="text-[26px] font-semibold tracking-tight text-slate-900">
              Ready to run intelligence workflows?
            </div>
            <p className="mt-2 text-[15px] leading-relaxed text-slate-600">
              Move from overview into search, graph traversal, and evidence-grounded narrative synthesis.
            </p>
            <div className="mt-6">
              <button
                onClick={onEnter}
                className="btn-primary inline-flex items-center gap-2 rounded-md px-6 py-3 text-sm font-semibold text-white transition-colors"
              >
                Launch Workspace
                <Workflow size={14} />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function PulseTile({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-md border border-slate-200/80 bg-white/76 px-4 py-3.5">
      <div className="mb-1.5 inline-flex h-7 w-7 items-center justify-center rounded-sm bg-blue-50 text-blue-700">
        <Icon size={13} />
      </div>
      <div className="text-[32px] font-semibold leading-[1.08] tracking-tight text-slate-900">
        <LiveNumber value={value} />
      </div>
      <div className="mt-1 text-[12px] text-slate-500">{label}</div>
    </div>
  );
}
