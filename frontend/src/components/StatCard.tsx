import { useAnimatedNumber } from '../hooks/useAnimatedNumber';

interface Props {
  value: number;
  label: string;
  suffix?: string;
  icon: React.ReactNode;
  delay?: number;
}

export default function StatCard({ value, label, suffix, icon, delay = 0 }: Props) {
  const animated = useAnimatedNumber(value, 1400 + delay);

  return (
    <div className="group relative overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03] p-5 backdrop-blur-sm hover:border-brand/20 transition-all duration-200">
      {/* Subtle gold accent on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-brand/0 to-brand/0 group-hover:from-brand/[0.04] group-hover:to-transparent transition-all duration-300" />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/[0.06] text-brand">
            {icon}
          </div>
        </div>
        <div className="text-2xl font-bold tracking-tight text-white tabular-nums">
          {animated.toLocaleString()}{suffix && <span className="text-sm font-medium text-white/40 ml-0.5">{suffix}</span>}
        </div>
        <div className="mt-1 text-xs text-neutral-500 font-medium">{label}</div>
      </div>
    </div>
  );
}
