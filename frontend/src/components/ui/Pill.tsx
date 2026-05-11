import { type ReactNode } from 'react';

type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info' | 'brand';

interface PillProps {
  label: string;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Pill({ label, tone = 'neutral', icon, className = '', onClick }: PillProps) {
  const toneClasses = {
    neutral: 'bg-surface-3 text-ink-2 border-line',
    good: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    warn: 'bg-amber-50 text-amber-800 border-amber-200',
    bad: 'bg-rose-50 text-rose-700 border-rose-200',
    info: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    brand: 'bg-ink text-white border-ink',
  };

  const baseClasses = 'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors';
  const interactiveClasses = onClick ? 'cursor-pointer hover:opacity-80' : '';

  return (
    <span 
      onClick={onClick}
      className={`${baseClasses} ${toneClasses[tone]} ${interactiveClasses} ${className}`}
    >
      {icon && <span className="opacity-75">{icon}</span>}
      {label}
    </span>
  );
}
