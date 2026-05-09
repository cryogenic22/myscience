import React from 'react';
import { motion } from 'framer-motion';

export interface TimelineItem {
  id: string;
  title: string;
  timestamp: string;
  status: 'past' | 'active' | 'future';
  content?: string;
}

export interface TimelineProps {
  items: TimelineItem[];
  className?: string;
}

export function Timeline({ items, className = '' }: TimelineProps) {
  return (
    <div className={`flex flex-col ${className}`}>
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        
        let dotColor = 'var(--color-line-2)';
        let textColor = 'var(--color-ink-3)';
        
        if (item.status === 'active') {
          dotColor = 'var(--color-accent)';
          textColor = 'var(--color-ink)';
        } else if (item.status === 'past') {
          dotColor = 'var(--color-ink-3)';
          textColor = 'var(--color-ink-2)';
        }

        return (
          <div key={item.id || index} className="relative flex gap-4 pb-6">
            {/* Vertical Line */}
            {!isLast && (
              <div 
                className="absolute top-5 bottom-0 w-px left-[9px]"
                style={{ backgroundColor: 'var(--color-line)' }}
              />
            )}
            
            {/* Dot */}
            <div className="relative mt-1">
              <motion.div 
                className="w-5 h-5 rounded-full border-4 shadow-sm"
                style={{ 
                  backgroundColor: 'var(--color-surface)',
                  borderColor: dotColor
                }}
                data-status={item.status}
                whileHover={{ scale: 1.2 }}
              />
              {item.status === 'active' && (
                <motion.div 
                  className="absolute inset-0 rounded-full"
                  style={{ backgroundColor: 'var(--color-accent)' }}
                  animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 flex flex-col pt-1">
              <div className="flex justify-between items-baseline mb-1">
                <span 
                  className="font-medium text-sm"
                  style={{ color: textColor }}
                >
                  {item.title}
                </span>
                <span 
                  className="text-xs font-mono"
                  style={{ color: 'var(--color-ink-4)' }}
                >
                  {item.timestamp}
                </span>
              </div>
              {item.content && (
                <p 
                  className="text-xs leading-relaxed"
                  style={{ color: 'var(--color-ink-3)' }}
                >
                  {item.content}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
