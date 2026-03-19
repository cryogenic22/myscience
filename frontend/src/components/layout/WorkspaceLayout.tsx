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
      if (!Number.isNaN(parsed) && parsed >= 20 && parsed <= 80) return parsed;
    }
  } catch { /* ignore */ }
  return fallback;
}

export default function WorkspaceLayout({
  left,
  right,
  defaultSplit = 42,
  minLeft = 28,
  minRight = 30,
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

  useEffect(() => {
    if (!isDragging) return;
    const prev = document.body.style.userSelect;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    return () => { document.body.style.userSelect = prev; document.body.style.cursor = ''; };
  }, [isDragging]);

  return (
    <>
      {/* Desktop: horizontal split */}
      <div
        ref={containerRef}
        className="hidden md:flex min-h-0 flex-1"
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {/* Left panel — chat */}
        <div className="flex flex-col overflow-hidden" style={{ width: `${split}%` }}>
          {left}
        </div>

        {/* Divider — nearly invisible, widens on hover */}
        <div
          className="group relative shrink-0 cursor-col-resize"
          onPointerDown={handlePointerDown}
        >
          {/* Hit area (wider than visual) */}
          <div className="absolute inset-y-0 -left-1.5 -right-1.5 z-10" />
          {/* Visual line */}
          <div className={`h-full w-px transition-colors duration-150 ${
            isDragging ? 'bg-brand/40' : 'bg-slate-200/80 group-hover:bg-brand/25 dark:bg-slate-700/60'
          }`} />
          {/* Grab handle dots — visible on hover */}
          <div className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-1 transition-opacity duration-150 ${
            isDragging ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          }`}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-1 w-1 rounded-full bg-slate-400/70" />
            ))}
          </div>
        </div>

        {/* Right panel — canvas */}
        <div className="flex flex-col overflow-hidden bg-surface dark:bg-slate-900/50" style={{ width: `${100 - split}%` }}>
          {right}
        </div>
      </div>

      {/* Mobile: stacked */}
      <div className="flex flex-1 flex-col md:hidden min-h-0">
        <div className="flex-1 overflow-y-auto">{left}</div>
        <div className="h-px bg-slate-200 dark:bg-slate-700" />
        <div className="flex-1 overflow-y-auto bg-surface dark:bg-slate-900/50">{right}</div>
      </div>
    </>
  );
}
