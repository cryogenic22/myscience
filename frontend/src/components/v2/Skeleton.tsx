import React from 'react';

interface SkeletonProps {
  variant?: 'line' | 'block' | 'circle';
  width?: string;
  height?: string;
  lines?: number;
}

const shimmerStyle: React.CSSProperties = {
  background: 'linear-gradient(90deg, var(--surface-secondary) 25%, var(--surface-elevated) 50%, var(--surface-secondary) 75%)',
  backgroundSize: '200% 100%',
  animation: 'shimmer 1.5s infinite linear',
};

export default function Skeleton({
  variant = 'line',
  width,
  height,
  lines = 1,
}: SkeletonProps) {
  if (variant === 'circle') {
    const diameter = width ?? '40px';
    return (
      <div
        style={{
          ...shimmerStyle,
          width: diameter,
          height: diameter,
          borderRadius: '50%',
          flexShrink: 0,
        }}
      />
    );
  }

  if (variant === 'block') {
    return (
      <div
        style={{
          ...shimmerStyle,
          width: width ?? '100%',
          height: height ?? '80px',
          borderRadius: 'var(--radius-md)',
        }}
      />
    );
  }

  // variant === 'line'
  const count = Math.max(1, lines);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          style={{
            ...shimmerStyle,
            width: width ?? '100%',
            height: height ?? '14px',
            borderRadius: 'var(--radius-sm)',
            opacity: 1 - i * 0.1,
          }}
        />
      ))}
    </div>
  );
}
