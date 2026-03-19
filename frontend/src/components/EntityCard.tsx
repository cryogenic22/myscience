import { Pill, Building2, FlaskConical, Dna, Target, FileText } from 'lucide-react';

interface Props {
  entityType: string;
  label: string;
  properties: Record<string, unknown>;
  connections?: number;
  onClick?: () => void;
}

const TYPE_CONFIG: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  drug: { icon: <Pill size={16} />, color: 'text-blue-600', bg: 'bg-blue-50' },
  company: { icon: <Building2 size={16} />, color: 'text-amber-600', bg: 'bg-amber-50' },
  trial: { icon: <FlaskConical size={16} />, color: 'text-teal-600', bg: 'bg-teal-50' },
  therapeutic_area: { icon: <Target size={16} />, color: 'text-rose-600', bg: 'bg-rose-50' },
  mechanism: { icon: <Dna size={16} />, color: 'text-violet-600', bg: 'bg-violet-50' },
  literature: { icon: <FileText size={16} />, color: 'text-green-600', bg: 'bg-green-50' },
};

export default function EntityCard({ entityType, label, properties, connections, onClick }: Props) {
  const cfg = TYPE_CONFIG[entityType] ?? TYPE_CONFIG.drug;

  const displayProps = Object.entries(properties)
    .filter(([k]) => !k.includes('embedding') && !k.includes('id'))
    .slice(0, 4);

  return (
    <div
      onClick={onClick}
      className={`rounded-md border border-slate-200/75 bg-white/88 px-4 py-4 shadow-sm transition-all ${onClick ? 'cursor-pointer hover:border-slate-300 hover:shadow-md' : ''}`}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5">
          <div className={`flex h-8 w-8 items-center justify-center rounded-full ${cfg.bg} ${cfg.color}`}>
            {cfg.icon}
          </div>
          <div>
            <div className="max-w-[14rem] truncate text-[13px] font-semibold leading-tight text-slate-900">{label}</div>
            <div className="text-[11px] text-slate-400 capitalize">{entityType.replace('_', ' ')}</div>
          </div>
        </div>
        {connections !== undefined && (
          <span className="rounded-md border border-slate-200/75 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500">
            {connections} links
          </span>
        )}
      </div>

      {displayProps.length > 0 && (
        <div className="space-y-1">
          {displayProps.map(([key, val]) => (
            <div key={key} className="flex items-baseline justify-between text-xs">
              <span className="text-slate-400 capitalize">{key.replace(/_/g, ' ')}</span>
              <span className="text-slate-600 font-medium truncate ml-2 max-w-[60%] text-right">
                {String(val ?? '--')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
