import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

interface WorkspaceLayoutProps {
  left: ReactNode;
  right: ReactNode;
  defaultSplit?: number;
  minLeft?: number;
  minRight?: number;
}

const STORAGE_KEY = 'mz-panel-split';

function readStoredSplit(fallback: number): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw !== null) {
      const parsed = parseFloat(raw);
      if (!Number.isNaN(parsed) && parsed >= 25 && parsed <= 75) return parsed;
    }
  } catch { /* ignore */ }
  return fallback;
}

export default function WorkspaceLayout({
  left,
  right,
  defaultSplit = 48,
  minLeft = 30,
  minRight = 25,
}: WorkspaceLayoutProps) {
  const [split, setSplit] = useState(() => readStoredSplit(defaultSplit));
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const persistSplit = useCallback((value: number) => {
    setSplit(value);
    try { localStorage.setItem(STORAGE_KEY, String(value)); } catch { /* */ }
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsDragging(true);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      persistSplit(Math.round(Math.min(Math.max(pct, minLeft), 100 - minRight) * 10) / 10);
    },
    [isDragging, minLeft, minRight, persistSplit],
  );

  const handlePointerUp = useCallback(() => setIsDragging(false), []);

  // Keyboard resize — the divider is a focusable ARIA separator so it isn't a
  // pointer-only control. Arrow keys nudge, Home/End jump to the clamps.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const STEP = 2;
      const lo = minLeft;
      const hi = 100 - minRight;
      let next: number | null = null;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = split - STEP;
      else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = split + STEP;
      else if (e.key === 'Home') next = lo;
      else if (e.key === 'End') next = hi;
      if (next === null) return;
      e.preventDefault();
      persistSplit(Math.round(Math.min(Math.max(next, lo), hi) * 10) / 10);
    },
    [split, minLeft, minRight, persistSplit],
  );

  useEffect(() => {
    if (!isDragging) return;
    const prev = document.body.style.userSelect;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    return () => {
      document.body.style.userSelect = prev;
      document.body.style.cursor = '';
    };
  }, [isDragging]);

  return (
    <>
      {/* Desktop: horizontal split */}
      <div
        ref={containerRef}
        className="hidden md:flex"
        style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {/* Left — chat */}
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: `${split}%` }}
        >
          {left}
        </div>

        {/* Divider */}
        <div
          className="group relative shrink-0 cursor-col-resize"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panels"
          aria-valuenow={Math.round(split)}
          aria-valuemin={minLeft}
          aria-valuemax={100 - minRight}
          tabIndex={0}
          onPointerDown={handlePointerDown}
          onKeyDown={handleKeyDown}
          style={{ width: '1px' }}
        >
          {/* wider hit area */}
          <div className="absolute inset-y-0 -left-2 -right-2 z-10" />
          {/* visual */}
          <div
            className="h-full transition-colors duration-150"
            style={{
              width: '1px',
              background: isDragging
                ? 'var(--color-accent)'
                : 'var(--color-line)',
            }}
          />
        </div>

        {/* Right — canvas */}
        <div
          className="flex flex-col overflow-hidden"
          style={{
            width: `${100 - split}%`,
            background: 'var(--color-surface-2)',
          }}
        >
          {right}
        </div>
      </div>

      {/* Mobile: stacked */}
      <div className="flex flex-1 flex-col md:hidden" style={{ minHeight: 0 }}>
        <div style={{ flex: 1, overflowY: 'auto' }}>{left}</div>
        <div style={{ height: '1px', background: 'var(--color-line)' }} />
        <div style={{ flex: 1, overflowY: 'auto', background: 'var(--color-surface-2)' }}>
          {right}
        </div>
      </div>
    </>
  );
}
