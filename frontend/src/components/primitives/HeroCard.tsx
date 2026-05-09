import React from 'react';
import { motion } from 'framer-motion';

export interface HeroCardProps {
  children: React.ReactNode;
  title?: string;
  className?: string;
}

export function HeroCard({ children, title, className = '' }: HeroCardProps) {
  return (
    <motion.div
      className={`rounded-xl overflow-hidden flex flex-col ${className}`}
      style={{
        backgroundColor: 'var(--color-surface-2)',
        boxShadow: 'var(--shadow-md)',
        border: '1px solid var(--color-line-2)'
      }}
      whileHover={{ y: -2, boxShadow: 'var(--shadow-lg)' }}
      transition={{ duration: 0.2 }}
    >
      {title && (
        <div 
          className="px-4 py-3 font-semibold text-xs border-b uppercase tracking-wider"
          style={{ 
            color: 'var(--color-ink)',
            borderColor: 'var(--color-line-2)',
            fontFamily: 'var(--font-display)'
          }}
        >
          {title}
        </div>
      )}
      <div className="p-4 flex-1">
        {children}
      </div>
    </motion.div>
  );
}
