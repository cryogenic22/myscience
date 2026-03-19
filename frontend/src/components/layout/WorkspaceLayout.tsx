import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

interface WorkspaceLayoutProps {
  left: ReactNode;
  right: ReactNode;
  defaultSplit?: number;   // 0-100, default 50
  minLeft?: number;        // min % for left panel, default 30
  minRight?: number;       // min % for right panel, default 25
}

const STORAGE_KEY = 'mz-panel-split';

function readStoredSplit(fallback: number): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw !== null) {
      const parsed = parseFloat(raw);
      if (!Number.isNaN(parsed) && parsed >= 10 && parsed <= 90) return parsed;
    }
  } catch { /* ignore storage errors */ }
  return fallback;
}

export default function WorkspaceLayout({
  left,
  right,
  defaultSplit = 50,
  minLeft = 30,
  minRight = 25,
}: WorkspaceLayoutProps) {
  const [split, setSplit] = useState(() => readStoredSplit(defaultSplit));
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const persistSplit = useCallback((value: number) => {
    setSplit(value);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch { /* ignore */ }
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
      const x = e.clientX - rect.left;
      const pct = (x / rect.width) * 100;
      const clamped = Math.min(Math.max(pct, minLeft), 100 - minRight);
      persistSplit(Math.round(clamped * 100) / 100);
    },
    [isDragging, minLeft, minRight, persistSplit],
  );

  const handlePointerUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Prevent text selection during drag
  useEffect(() => {
    if (!isDragging) return;
    const style = document.body.style;
    const prev = style.userSelect;
    style.userSelect = 'none';
    return () => {
      style.userSelect = prev;
    };
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
        {/* Left panel */}
        <div
          className="flex flex-col overflow-y-auto"
          style={{ width: `${split}%` }}
        >
          {left}
        </div>

        {/* Divider */}
        <div
          className={`relative w-1 shrink-0 cursor-col-resize transition-colors ${
            isDragging ? 'bg-brand/30' : 'bg-slate-200 hover:bg-brand/20'
          }`}
          onPointerDown={handlePointerDown}
        >
          {/* Drag handle indicator */}
          <div className="absolute inset-y-0 -left-1 -right-1" />
        </div>

        {/* Right panel */}
        <div
          className="flex flex-col overflow-y-auto"
          style={{ width: `${100 - split}%` }}
        >
          {right}
        </div>
      </div>

      {/* Mobile: stacked vertically */}
      <div className="flex flex-1 flex-col md:hidden min-h-0 overflow-y-auto">
        <div className="flex-1 overflow-y-auto border-b border-slate-200">
          {left}
        </div>
        <div className="flex-1 overflow-y-auto">
          {right}
        </div>
      </div>
    </>
  );
}
