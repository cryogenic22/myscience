import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface AgentStatusBarProps {
  status: 'idle' | 'sensing' | 'framing' | 'simulating';
  message: string;
  agentCount?: number;
  className?: string;
}

export function AgentStatusBar({ status, message, agentCount = 0, className = '' }: AgentStatusBarProps) {
  let statusColor = 'var(--color-ink-3)';
  let dotAnimation = {};

  if (status === 'sensing') {
    statusColor = 'var(--color-green)';
    dotAnimation = { opacity: [0.3, 1], scale: [0.8, 1.2] };
  } else if (status === 'framing') {
    statusColor = 'var(--color-amber)';
    dotAnimation = { opacity: [0.5, 1], rotate: 180 };
  } else if (status === 'simulating') {
    statusColor = 'var(--color-accent)';
    dotAnimation = { scale: [1, 1.5], opacity: [1, 0] };
  }

  return (
    <div 
      className={`flex items-center justify-between px-4 py-2 rounded-lg border text-xs font-mono uppercase tracking-widest ${className}`}
      style={{ 
        backgroundColor: 'var(--color-surface-2)',
        borderColor: 'var(--color-line-2)',
        color: 'var(--color-ink-2)'
      }}
      data-status={status}
    >
      <div className="flex items-center gap-3">
        <div className="relative w-2 h-2">
          <motion.div 
            className="absolute inset-0 rounded-full"
            style={{ backgroundColor: statusColor }}
            animate={dotAnimation}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>
        <AnimatePresence mode="wait">
          <motion.span
            key={message}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.3 }}
          >
            {message}
          </motion.span>
        </AnimatePresence>
      </div>
      
      {agentCount > 0 && (
        <div className="flex items-center gap-2">
          <span style={{ color: 'var(--color-ink-3)' }}>{agentCount} Agents Active</span>
        </div>
      )}
    </div>
  );
}
