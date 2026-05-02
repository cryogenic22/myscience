import type { WarRoomReaction } from '../../../api';

interface Props {
  scores: WarRoomReaction['scores'];
}

const DIMENSIONS: Array<{
  key: keyof NonNullable<WarRoomReaction['scores']>;
  label: string;
  unit: string;
  min: number;
  max: number;
  color: string;
}> = [
  { key: 'market_share_delta',     label: 'Mkt Share Δ', unit: 'pts', min: -10,  max: 10,   color: '#3B82F6' },
  { key: 'time_to_execute_months', label: 'Time',        unit: 'mo',  min: 1,    max: 36,   color: '#A78BFA' },
  { key: 'capex_required_musd',    label: 'Capex',       unit: '$M',  min: 50,   max: 3000, color: '#F59E0B' },
  { key: 'regulatory_risk',        label: 'Reg Risk',    unit: '/10', min: 1,    max: 10,   color: '#EF4444' },
  { key: 'payer_acceptance',       label: 'Payer',       unit: '/10', min: 1,    max: 10,   color: '#10B981' },
];

export default function ScoreBars({ scores }: Props) {
  return (
    <div className="grid grid-cols-5 gap-2">
      {DIMENSIONS.map((d) => {
        const v = scores[d.key];
        const num = typeof v === 'number' ? v : 0;
        // Normalize 0-1 for bar width (handle negative for market_share_delta)
        let pct: number;
        if (d.key === 'market_share_delta') {
          pct = ((num - d.min) / (d.max - d.min)) * 100;
        } else {
          pct = ((num - d.min) / (d.max - d.min)) * 100;
        }
        pct = Math.max(0, Math.min(100, pct));
        const display = d.key === 'capex_required_musd' ? `$${Math.round(num)}M`
          : d.key === 'market_share_delta' ? `${num > 0 ? '+' : ''}${num.toFixed(1)}${d.unit === 'pts' ? '' : d.unit}`
          : `${Math.round(num)}${d.unit === '/10' ? '' : ' ' + d.unit}`;
        return (
          <div key={d.key}>
            <div className="text-[9px] uppercase font-medium" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}>
              {d.label}
            </div>
            <div className="text-[12px] font-medium mt-0.5" style={{ color: 'var(--color-ink)' }}>
              {display}
            </div>
            <div
              className="mt-1 h-1.5 rounded-full overflow-hidden"
              style={{ background: 'var(--color-surface-2)' }}
            >
              <div style={{
                width: `${pct}%`,
                height: '100%',
                background: d.color,
                transition: 'width 200ms ease',
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
