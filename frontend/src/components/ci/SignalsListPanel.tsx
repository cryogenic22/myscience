import { useEffect, useRef } from 'react';
import type { Signal } from '../../api';
import SignalCard from './SignalCard';

interface Props {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  emptyMessage?: React.ReactNode;
}

export default function SignalsListPanel({
  signals, selectedId, onSelect, emptyMessage,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Keyboard nav: j (next), k (prev)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
      if (e.key !== 'j' && e.key !== 'k') return;
      if (signals.length === 0) return;
      const idx = signals.findIndex((s) => s.id === selectedId);
      if (e.key === 'j') {
        const next = idx < 0 ? 0 : Math.min(idx + 1, signals.length - 1);
        onSelect(signals[next].id);
      } else {
        const prev = idx <= 0 ? 0 : idx - 1;
        onSelect(signals[prev].id);
      }
      e.preventDefault();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [signals, selectedId, onSelect]);

  if (signals.length === 0) {
    return (
      <div
        ref={containerRef}
        className="overflow-y-auto"
        style={{
          width: '380px',
          borderRight: '1px solid var(--color-line)',
          background: 'var(--color-surface-2)',
        }}
      >
        <div className="p-6 text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
          {emptyMessage ?? 'No signals match the current filters.'}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="overflow-y-auto"
      style={{
        width: '380px',
        borderRight: '1px solid #23262d',
        background: '#0a0b0e',
      }}
    >
      {signals.map((s) => (
        <SignalCard
          key={s.id}
          signal={s}
          selected={s.id === selectedId}
          onSelect={() => onSelect(s.id)}
        />
      ))}
    </div>
  );
}
