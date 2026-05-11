import { ExternalLink, Database, Network, BarChart3 } from 'lucide-react';

interface Props {
  source: string;
  entityType: string;
  content: string;
  relevance: number;
  provenance: Record<string, unknown>;
  index?: number;
  highlighted?: boolean;
}

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  search: <Database size={12} />,
  graph: <Network size={12} />,
  metrics: <BarChart3 size={12} />,
};

const SOURCE_COLORS: Record<string, string> = {
  search: 'text-blue-600 bg-blue-50',
  graph: 'text-violet-600 bg-violet-50',
  metrics: 'text-amber-600 bg-amber-50',
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  clinical_trials_gov: 'Clinical Trial',
  clinicaltrials_gov: 'Clinical Trial',
  pubmed: 'Publication',
  fda_orange_book: 'FDA Orange Book',
  fda_approvals: 'FDA Approval',
  dailymed: 'Drug Label',
  openfda: 'OpenFDA',
  mesh: 'MeSH Ontology',
  unii: 'UNII Substance',
  drugbank: 'DrugBank',
};

function freshnessBadge(provenance: Record<string, unknown>): { label: string; color: string } | null {
  const retrieved = provenance?.retrieved_at as string | undefined;
  if (!retrieved) return null;
  const days = Math.floor((Date.now() - new Date(retrieved).getTime()) / 86_400_000);
  if (days < 0 || isNaN(days)) return null;
  if (days <= 7) return { label: 'Fresh', color: 'text-emerald-700 bg-emerald-50' };
  if (days <= 30) return { label: 'Recent', color: 'text-blue-700 bg-blue-50' };
  if (days <= 90) return { label: `${days}d ago`, color: 'text-amber-700 bg-amber-50' };
  return { label: `${Math.floor(days / 30)}mo ago`, color: 'text-slate-500 bg-slate-100' };
}

export default function EvidenceCard({ source, entityType, content, relevance, provenance, index, highlighted }: Props) {
  const sourceApi = provenance?.source_api as string | undefined;
  const sourceUrl = provenance?.source_url as string | undefined;
  const sourceTypeLabel = SOURCE_TYPE_LABELS[(sourceApi ?? '').toLowerCase()] ?? sourceApi;
  const freshness = freshnessBadge(provenance ?? {});

  return (
    <div className={`rounded-md border border-slate-200/75 bg-white/88 mz-text-sm shadow-sm transition-all ${
      highlighted ? 'ring-2 ring-brand/10' : 'hover:border-slate-300 hover:shadow-md'
    }`} style={{ padding: '14px 16px' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {index !== undefined && (
            <span className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-200 bg-slate-50 mz-text-xs font-bold text-slate-500">
              {index}
            </span>
          )}
          <span className={`flex items-center gap-1 rounded-sm mz-text-xs font-medium ${SOURCE_COLORS[source] ?? SOURCE_COLORS.search}`} style={{ padding: '4px 10px' }}>
            {SOURCE_ICONS[source] ?? SOURCE_ICONS.search}
            {source}
          </span>
          <span className="mz-text-xs text-slate-400 capitalize">{entityType.replace('_', ' ')}</span>
          {sourceTypeLabel && (
            <span className="rounded-sm bg-slate-100 mz-text-xs text-slate-500" style={{ padding: '2px 6px' }}>
              {sourceTypeLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {freshness && (
            <span className={`rounded-sm mz-text-xs font-medium ${freshness.color}`} style={{ padding: '2px 6px' }}>
              {freshness.label}
            </span>
          )}
          <span className="mz-text-xs font-medium text-slate-400">
            {(relevance * 100).toFixed(0)}% relevant
          </span>
        </div>
      </div>
      <p className="text-slate-600 leading-relaxed line-clamp-3">{content}</p>
      {(sourceApi || sourceUrl) && (
        <div className="mt-2 flex items-center gap-1 mz-text-xs text-slate-400">
          <ExternalLink size={10} />
          {sourceUrl ? (
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-brand-dark hover:underline truncate">
              {sourceApi || sourceUrl}
            </a>
          ) : (
            <span>{sourceApi}</span>
          )}
        </div>
      )}
    </div>
  );
}
