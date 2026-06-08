import { motion } from 'framer-motion';

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
}

export function Sparkline({
  data,
  width = 100,
  height = 30,
  strokeWidth = 2,
}: SparklineProps) {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  // Add some padding to the range so points aren't cut off by stroke width at the extremes
  const paddingY = strokeWidth;
  const usableHeight = height - paddingY * 2;
  const range = max - min || 1;

  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - paddingY - ((d - min) / range) * usableHeight;
    return `${x},${y}`;
  });

  // Calculate semantic color based on first vs last point
  const first = data[0];
  const last = data[data.length - 1];
  let semanticColor = 'ink';
  let colorVar = 'var(--color-ink-3)';

  if (last > first) {
    semanticColor = 'green';
    colorVar = 'var(--color-green)';
  } else if (last < first) {
    semanticColor = 'red';
    colorVar = 'var(--color-red)';
  }

  const pathD = `M ${pts.join(' L ')}`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <motion.path
        d={pathD}
        fill="none"
        stroke={colorVar}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1, ease: 'easeInOut' }}
        data-semantic-color={semanticColor}
      />
    </svg>
  );
}
