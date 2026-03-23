import { TrendingUp, BarChart3, BookOpen, Target, Building2 } from 'lucide-react';

interface Props {
  type: 'pipeline' | 'success_rate' | 'evidence' | 'competitive' | 'portfolio';
  data: Record<string, unknown>;
  entityName?: string;
}

const ICONS: Record<string, React.ReactNode> = {
  pipeline: <BarChart3 size={14} />,
  success_rate: <TrendingUp size={14} />,
  evidence: <BookOpen size={14} />,
  competitive: <Target size={14} />,
  portfolio: <Building2 size={14} />,
};

const LABELS: Record<string, string> = {
  pipeline: 'Pipeline Strength',
  success_rate: 'Trial Success Rate',
  evidence: 'Evidence Density',
  competitive: 'Competitive Position',
  portfolio: 'Company Portfolio',
};

export default function MetricCard({ type, data, entityName }: Props) {
  return (
    <div className="rounded-md border border-slate-200/75 bg-white/88 shadow-sm transition-all hover:border-slate-300 hover:shadow-md" style={{ padding: '10px 12px' }}>
      {/* Header row: icon + type label */}
      <div className="mb-1.5 flex items-center gap-2">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand-dark">
          {ICONS[type]}
        </div>
        <span className="flex-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          {LABELS[type]}
        </span>
      </div>

      {/* Entity name */}
      {entityName && (
        <div className="mb-1.5 truncate text-[12px] font-semibold text-slate-800" style={{ paddingLeft: '32px' }}>
          {entityName}
        </div>
      )}

      {/* Summary metrics */}
      <div className="space-y-1 text-[12px]">
        {type === 'pipeline' && <PipelineSummary data={data} />}
        {type === 'success_rate' && <SuccessRateSummary data={data} />}
        {type === 'evidence' && <EvidenceSummary data={data} />}
        {type === 'competitive' && <CompetitiveSummary data={data} />}
        {type === 'portfolio' && <PortfolioSummary data={data} />}
      </div>
    </div>
  );
}

/* Summary views (compact) */

function PipelineSummary({ data }: { data: Record<string, unknown> }) {
  const counts = [
    Number(data.p1_count ?? 0),
    Number(data.p2_count ?? 0),
    Number(data.p3_count ?? 0),
    Number(data.p4_count ?? 0),
  ];
  const maxCount = Math.max(...counts, 1);

  return (
    <>
      <MetricRow label="Pipeline Score" value={data.pipeline_score} bold />
      <MetricRow label="Total Trials" value={data.total_trials ?? data.active_trials} />
      <div className="mt-1.5 flex gap-1.5">
        <PhaseBar label="P1" count={counts[0]} max={maxCount} color="bg-blue-500" />
        <PhaseBar label="P2" count={counts[1]} max={maxCount} color="bg-teal-500" />
        <PhaseBar label="P3" count={counts[2]} max={maxCount} color="bg-brand" />
        <PhaseBar label="P4" count={counts[3]} max={maxCount} color="bg-green-500" />
      </div>
    </>
  );
}

function SuccessRateSummary({ data }: { data: Record<string, unknown> }) {
  const raw = Number(data.success_rate ?? 0);
  const rate = raw <= 1 ? raw * 100 : raw;
  return (
    <>
      <MetricRow label="Success Rate" value={`${rate.toFixed(1)}%`} bold />
      <div className="mb-1 mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-green-500 transition-all duration-700"
          style={{ width: `${Math.min(rate, 100)}%` }}
        />
      </div>
      <MetricRow label="Completed" value={data.completed} />
      {Number(data.active ?? 0) > 0 && <MetricRow label="Active" value={data.active} />}
      <MetricRow label="Terminated" value={data.terminated} />
    </>
  );
}

function EvidenceSummary({ data }: { data: Record<string, unknown> }) {
  return (
    <>
      <MetricRow label="Total Articles" value={data.total_articles} bold />
      <MetricRow label="Recent (2yr)" value={data.recent_count} />
      <MetricRow label="Weighted Score" value={Number(data.weighted_score ?? 0).toFixed(1)} />
    </>
  );
}

function CompetitiveSummary({ data }: { data: Record<string, unknown> }) {
  return (
    <>
      <MetricRow label="Mechanism" value={data.mechanism_name} bold />
      <MetricRow label="Drug Count" value={data.drug_count} />
      <MetricRow label="Active Trials" value={data.active_trial_count} />
      <MetricRow label="Top Drug" value={data.top_drug} />
    </>
  );
}

function PortfolioSummary({ data }: { data: Record<string, unknown> }) {
  return (
    <>
      <MetricRow label="Drugs" value={data.drug_count} bold />
      <MetricRow label="Trials" value={data.trial_count} />
      <MetricRow label="Active" value={data.active_trial_count} />
      <MetricRow label="Pipeline Score" value={Number(data.pipeline_score_total ?? 0).toFixed(0)} />
    </>
  );
}

/* Shared helpers */

function MetricRow({ label, value, bold }: { label: string; value: unknown; bold?: boolean }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={bold ? 'text-[14px] font-semibold text-slate-900' : 'font-medium text-slate-600'}>
        {formatValue(value)}
      </span>
    </div>
  );
}

function PhaseBar({ label, count, max, color }: { label: string; count: number; max: number; color: string }) {
  const pct = Math.min((count / max) * 100, 100);
  return (
    <div className="flex-1">
      <div className="mb-0.5 text-center text-[10px] text-slate-400">{label}</div>
      <div className="relative h-7 overflow-hidden rounded-md bg-slate-100">
        <div
          className={`absolute bottom-0 left-0 right-0 ${color} rounded-md transition-all duration-700`}
          style={{ height: `${pct}%` }}
        />
      </div>
      <div className="mt-0.5 text-center text-[10px] font-medium text-slate-600">{count}</div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '--';
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  const s = String(v);
  return s.length > 40 ? `${s.slice(0, 38)}..` : s;
}
