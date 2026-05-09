import React from 'react';
import { HeroCard } from './HeroCard';
import { ConfidenceBadge } from './ConfidenceBadge';

export interface DisagreementOption {
  id: string;
  name: string;
  claim: string;
  qualityScore: number;
}

export interface DisagreementPanelProps {
  topic: string;
  options: DisagreementOption[];
  onResolve: (selectedId: string) => void;
  className?: string;
}

export function DisagreementPanel({ topic, options, onResolve, className = '' }: DisagreementPanelProps) {
  // Sort options by quality score descending
  const sortedOptions = [...options].sort((a, b) => b.qualityScore - a.qualityScore);

  return (
    <HeroCard title={`CONFLICT: ${topic}`} className={className}>
      <div className="flex gap-4">
        {sortedOptions.map(opt => (
          <div 
            key={opt.id} 
            className="flex-1 p-4 rounded-lg border flex flex-col gap-3"
            style={{ 
              borderColor: 'var(--color-line-2)',
              backgroundColor: 'var(--color-surface)'
            }}
          >
            <div className="flex justify-between items-start">
              <span className="font-semibold text-sm" style={{ color: 'var(--color-ink)' }}>{opt.name}</span>
              <ConfidenceBadge value={opt.qualityScore / 100} label="Source Quality" />
            </div>
            
            <p className="text-sm flex-1" style={{ color: 'var(--color-ink-2)' }}>
              "{opt.claim}"
            </p>

            <button
              onClick={() => onResolve(opt.id)}
              className="mt-2 w-full py-2 rounded text-xs font-semibold uppercase tracking-wider transition-opacity cursor-pointer hover:opacity-90"
              style={{ 
                backgroundColor: 'var(--color-accent)', 
                color: '#fff' 
              }}
            >
              Accept
            </button>
          </div>
        ))}
      </div>
    </HeroCard>
  );
}
