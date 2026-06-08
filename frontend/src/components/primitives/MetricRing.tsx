import { motion } from 'framer-motion';

export interface MetricRingProps {
  value: number; // 0 to 100
  size?: number; // diameter in px
  strokeWidth?: number;
  showValue?: boolean;
}

export function MetricRing({
  value,
  size = 64,
  strokeWidth = 6,
  showValue = true,
}: MetricRingProps) {
  const clampedValue = Math.min(100, Math.max(0, value));
  
  // Semantic color logic
  let semanticColor = 'red';
  let colorVar = 'var(--color-red)';
  if (clampedValue >= 80) {
    semanticColor = 'green';
    colorVar = 'var(--color-green)';
  } else if (clampedValue >= 50) {
    semanticColor = 'amber';
    colorVar = 'var(--color-amber)';
  }

  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const strokeDashoffset = circumference - (clampedValue / 100) * circumference;

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={strokeWidth}
        />
        {/* Progress stroke with Framer Motion */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colorVar}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1, ease: 'easeOut' }}
          data-semantic-color={semanticColor}
        />
      </svg>
      {showValue && (
        <div
          className="absolute inset-0 flex items-center justify-center font-mono text-sm font-medium"
          style={{ color: 'var(--color-ink)' }}
        >
          {Math.round(clampedValue)}%
        </div>
      )}
    </div>
  );
}
