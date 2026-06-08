import { motion } from 'framer-motion';

export interface ConfidenceBadgeProps {
  value: number; // 0 to 1
  label?: string;
  className?: string;
}

export function ConfidenceBadge({ value, label = 'Confidence', className = '' }: ConfidenceBadgeProps) {
  const percentage = Math.round(value * 100);
  
  let semanticColor = 'red';
  let colorVar = 'var(--color-red)';
  
  if (percentage >= 80) {
    semanticColor = 'green';
    colorVar = 'var(--color-green)';
  } else if (percentage >= 50) {
    semanticColor = 'amber';
    colorVar = 'var(--color-amber)';
  }

  return (
    <motion.div 
      className={`inline-flex items-center gap-2 px-2 py-0.5 rounded text-xs font-mono font-medium border ${className}`}
      style={{ 
        color: colorVar, 
        borderColor: colorVar,
        backgroundColor: 'var(--color-surface)'
      }}
      data-semantic-color={semanticColor}
      title={`${label}: ${percentage}%`}
      whileHover={{ scale: 1.05 }}
    >
      <div 
        className="w-1.5 h-1.5 rounded-full" 
        style={{ backgroundColor: colorVar }}
      />
      {percentage}%
    </motion.div>
  );
}
