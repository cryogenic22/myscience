import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface EvidenceData {
  source: string;
  timestamp: string;
  passage: string;
  agentReasoning?: string;
  contradictions?: string[];
}

export interface EvidenceAffordanceProps {
  claimId: string;
  evidenceData: EvidenceData;
}

export function EvidenceAffordance({ evidenceData }: EvidenceAffordanceProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative inline-block ml-2 align-middle">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        aria-label="View Evidence"
        className="text-xs px-1.5 rounded cursor-pointer transition-colors border"
        style={{ 
          color: 'var(--color-ink-3)',
          borderColor: 'var(--color-line-2)',
          backgroundColor: isOpen ? 'var(--color-surface-2)' : 'transparent',
          lineHeight: '1.2'
        }}
      >
        ❖
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 5, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 5, scale: 0.95 }}
            className="absolute z-50 left-0 mt-2 w-80 p-4 rounded-xl flex flex-col gap-3 border text-left"
            style={{ 
              backgroundColor: 'var(--color-surface)',
              borderColor: 'var(--color-line-2)',
              boxShadow: 'var(--shadow-lg)'
            }}
          >
            <div className="flex justify-between items-center border-b pb-2" style={{ borderColor: 'var(--color-divider)' }}>
              <span className="font-semibold text-xs uppercase tracking-wider" style={{ color: 'var(--color-ink)', fontFamily: 'var(--font-display)' }}>Evidence Chain</span>
              <button onClick={() => setIsOpen(false)} className="text-xs cursor-pointer" style={{ color: 'var(--color-ink-3)' }}>✕</button>
            </div>
            
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--color-ink-3)' }}>SOURCE</span>
              <span className="text-sm font-medium" style={{ color: 'var(--color-accent)' }}>{evidenceData.source}</span>
              <span className="text-xs font-mono" style={{ color: 'var(--color-ink-4)' }}>{evidenceData.timestamp}</span>
            </div>

            <div className="flex flex-col gap-1 p-2 rounded" style={{ backgroundColor: 'var(--color-surface-2)' }}>
              <span className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--color-ink-3)' }}>EXACT PASSAGE</span>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--color-ink)' }}>"{evidenceData.passage}"</p>
            </div>

            {evidenceData.agentReasoning && (
              <div className="flex flex-col gap-1 mt-1">
                <span className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--color-ink-3)' }}>AGENT REASONING</span>
                <p className="text-xs italic" style={{ color: 'var(--color-ink-2)' }}>{evidenceData.agentReasoning}</p>
              </div>
            )}
            
            {evidenceData.contradictions && evidenceData.contradictions.length > 0 && (
              <div className="flex flex-col gap-1 mt-1 p-2 border rounded" style={{ borderColor: 'var(--color-red)' }}>
                <span className="text-[10px] font-mono tracking-widest" style={{ color: 'var(--color-red)' }}>CONTRADICTING SIGNALS</span>
                <ul className="list-disc pl-4 text-xs" style={{ color: 'var(--color-ink-2)' }}>
                  {evidenceData.contradictions.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
