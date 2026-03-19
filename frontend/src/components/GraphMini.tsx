import { useCallback, useEffect, useRef, useState } from 'react';
import type { GraphEdge, GraphNode } from '../api';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  centerEntityId?: string;
  height?: number;
  onNodeClick?: (node: GraphNode) => void;
}

const TYPE_COLORS: Record<string, string> = {
  drug: '#2563eb',
  company: '#d97706',
  trial: '#0d9488',
  therapeutic_area: '#e11d48',
  mechanism: '#7c3aed',
  literature: '#16a34a',
};

const TYPE_LABELS: Record<string, string> = {
  drug: 'Drug',
  company: 'Company',
  trial: 'Trial',
  therapeutic_area: 'Ther. Area',
  mechanism: 'Mechanism',
  literature: 'Literature',
};

type Viewport = { zoom: number; offsetX: number; offsetY: number };

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx?: number;
  fy?: number;
  edgeCount: number;
}

interface HitNode {
  x: number;
  y: number;
  radius: number;
  edgeCount: number;
  node: GraphNode;
}

function edgeSource(e: Record<string, unknown>): string {
  return String(e.source_id ?? e.source ?? '');
}

function edgeTarget(e: Record<string, unknown>): string {
  return String(e.target_id ?? e.target ?? '');
}

function edgeType(e: Record<string, unknown>): string {
  return String(e.link_type ?? e.type ?? '');
}

function clampZoom(raw: number): number {
  return Math.max(0.55, Math.min(2.6, raw));
}

export default function GraphMini({ nodes, edges, centerEntityId, height = 280, onNodeClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const drawRef = useRef<() => void>(() => {});
  const viewportRef = useRef<Viewport>({ zoom: 1, offsetX: 0, offsetY: 0 });
  const hitNodesRef = useRef<HitNode[]>([]);
  const hoveredNodeIdRef = useRef<string | null>(null);
  const dragRef = useRef<{ dragging: boolean; pointerId: number | null; lastX: number; lastY: number }>({
    dragging: false,
    pointerId: null,
    lastX: 0,
    lastY: 0,
  });
  const [zoomPct, setZoomPct] = useState(100);
  const [dragging, setDragging] = useState(false);
  const [hoverInfo, setHoverInfo] = useState<{ x: number; y: number; label: string; entityType: string; edgeCount: number } | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());

  const toggleType = useCallback((type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const pickHitNode = useCallback((x: number, y: number): HitNode | null => {
    let best: HitNode | null = null;
    let bestDist = Number.POSITIVE_INFINITY;
    for (const hit of hitNodesRef.current) {
      const dx = hit.x - x;
      const dy = hit.y - y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= hit.radius + 5 && dist < bestDist) {
        best = hit;
        bestDist = dist;
      }
    }
    return best;
  }, []);

  const panBy = useCallback((dx: number, dy: number) => {
    const viewport = viewportRef.current;
    viewport.offsetX += dx;
    viewport.offsetY += dy;
    drawRef.current();
  }, []);

  const zoomByFactor = useCallback((factor: number, anchor?: { x: number; y: number }) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const ax = anchor?.x ?? rect.width / 2;
    const ay = anchor?.y ?? rect.height / 2;

    const viewport = viewportRef.current;
    const nextZoom = clampZoom(viewport.zoom * factor);
    const worldX = (ax - viewport.offsetX) / viewport.zoom;
    const worldY = (ay - viewport.offsetY) / viewport.zoom;
    viewport.zoom = nextZoom;
    viewport.offsetX = ax - worldX * nextZoom;
    viewport.offsetY = ay - worldY * nextZoom;
    setZoomPct(Math.round(nextZoom * 100));
    drawRef.current();
  }, []);

  const resetView = useCallback(() => {
    viewportRef.current = { zoom: 1, offsetX: 0, offsetY: 0 };
    setZoomPct(100);
    drawRef.current();
  }, []);

  const handleCanvasClick = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onNodeClick) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const best = pickHitNode(x, y);
    if (best) onNodeClick(best.node);
  }, [onNodeClick, pickHitNode]);

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.button !== 0) return;
    dragRef.current = {
      dragging: true,
      pointerId: event.pointerId,
      lastX: event.clientX,
      lastY: event.clientY,
    };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus();
  }, []);

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (drag.dragging && drag.pointerId === event.pointerId) {
      const dx = event.clientX - drag.lastX;
      const dy = event.clientY - drag.lastY;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
      panBy(dx, dy);
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const hit = pickHitNode(x, y);
    const nextHoverId = hit?.node.entity_id ?? null;
    if (hoveredNodeIdRef.current !== nextHoverId) {
      hoveredNodeIdRef.current = nextHoverId;
      drawRef.current();
    }
    if (hit) {
      setHoverInfo({
        x: Math.min(rect.width - 12, x + 14),
        y: Math.min(rect.height - 8, y + 14),
        label: hit.node.label,
        entityType: hit.node.entity_type,
        edgeCount: hit.edgeCount,
      });
    } else if (hoverInfo) {
      setHoverInfo(null);
    }
  }, [panBy, pickHitNode, hoverInfo]);

  const handlePointerUp = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (drag.pointerId !== event.pointerId) return;
    dragRef.current = { dragging: false, pointerId: null, lastX: 0, lastY: 0 };
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const handlePointerLeave = useCallback(() => {
    if (hoveredNodeIdRef.current !== null) {
      hoveredNodeIdRef.current = null;
      drawRef.current();
    }
    setHoverInfo(null);
  }, []);

  const handleWheel = useCallback((event: React.WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    zoomByFactor(event.deltaY > 0 ? 0.9 : 1.12, {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    });
  }, [zoomByFactor]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLCanvasElement>) => {
    const key = event.key;
    if (key === 'ArrowLeft') {
      event.preventDefault();
      panBy(-22, 0);
      return;
    }
    if (key === 'ArrowRight') {
      event.preventDefault();
      panBy(22, 0);
      return;
    }
    if (key === 'ArrowUp') {
      event.preventDefault();
      panBy(0, -22);
      return;
    }
    if (key === 'ArrowDown') {
      event.preventDefault();
      panBy(0, 22);
      return;
    }
    if (key === '+' || key === '=') {
      event.preventDefault();
      zoomByFactor(1.12);
      return;
    }
    if (key === '-' || key === '_') {
      event.preventDefault();
      zoomByFactor(0.9);
      return;
    }
    if (key === '0') {
      event.preventDefault();
      resetView();
    }
  }, [panBy, zoomByFactor, resetView]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;
    hoveredNodeIdRef.current = null;
    setHoverInfo(null);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = rect.width;
    const h = rect.height;
    const legendH = 28;
    const cx = w / 2;
    const cy = legendH + (h - legendH) / 2;

    const edgeCounts = new Map<string, number>();
    for (const e of edges) {
      const s = edgeSource(e as unknown as Record<string, unknown>);
      const t = edgeTarget(e as unknown as Record<string, unknown>);
      edgeCounts.set(s, (edgeCounts.get(s) ?? 0) + 1);
      edgeCounts.set(t, (edgeCounts.get(t) ?? 0) + 1);
    }

    const visibleNodes = nodes.filter((n) => !hiddenTypes.has(n.entity_type));
    const keyNodes = visibleNodes.filter((node) =>
      node.entity_id === centerEntityId
      || node.entity_type !== 'drug'
      || (edgeCounts.get(node.entity_id) ?? 0) > 1
    );
    const displayNodes = keyNodes.length > 3 ? keyNodes.slice(0, 30) : visibleNodes.slice(0, 30);

    const simNodes: SimNode[] = displayNodes.map((node, index) => {
      const isCenter = node.entity_id === centerEntityId;
      const angle = (2 * Math.PI * index) / Math.max(displayNodes.length, 1);
      const baseR = node.entity_type === 'drug' ? 50 + Math.random() * 30 : 82 + Math.random() * 32;
      const dist = isCenter ? 0 : baseR;
      return {
        ...node,
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
        vx: 0,
        vy: 0,
        edgeCount: edgeCounts.get(node.entity_id) ?? 0,
        ...(isCenter ? { fx: cx, fy: cy } : {}),
      };
    });

    const nodeMap = new Map(simNodes.map((node) => [node.entity_id, node]));
    const visibleTypes = new Set(simNodes.map((node) => node.entity_type));

    const toScreen = (worldX: number, worldY: number) => {
      const v = viewportRef.current;
      return {
        x: worldX * v.zoom + v.offsetX,
        y: worldY * v.zoom + v.offsetY,
      };
    };

    const draw = (advancePhysics: boolean) => {
      if (advancePhysics) {
        for (const node of simNodes) {
          if (node.fx !== undefined) {
            node.x = node.fx;
            node.y = node.fy!;
            continue;
          }
          node.vx += (cx - node.x) * 0.002;
          node.vy += (cy - node.y) * 0.002;
          for (const other of simNodes) {
            if (node === other) continue;
            const dx = node.x - other.x;
            const dy = node.y - other.y;
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
            const force = 300 / (dist * dist);
            node.vx += (dx / dist) * force;
            node.vy += (dy / dist) * force;
          }
          for (const edge of edges) {
            const es = edgeSource(edge as unknown as Record<string, unknown>);
            const et = edgeTarget(edge as unknown as Record<string, unknown>);
            let other: SimNode | undefined;
            if (es === node.entity_id) other = nodeMap.get(et);
            if (et === node.entity_id) other = nodeMap.get(es);
            if (!other) continue;
            const dx = other.x - node.x;
            const dy = other.y - node.y;
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
            const force = (dist - 60) * 0.008;
            node.vx += (dx / dist) * force;
            node.vy += (dy / dist) * force;
          }
          node.vx *= 0.82;
          node.vy *= 0.82;
          node.x = Math.max(30, Math.min(w - 30, node.x + node.vx));
          node.y = Math.max(legendH + 20, Math.min(h - 20, node.y + node.vy));
        }
      }

      ctx.clearRect(0, 0, w, h);

      let lx = 8;
      ctx.font = '9px Inter, sans-serif';
      for (const type of visibleTypes) {
        const color = TYPE_COLORS[type] ?? '#9b9bab';
        const label = TYPE_LABELS[type] ?? type;
        ctx.beginPath();
        ctx.arc(lx + 5, 12, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.fillStyle = 'rgba(255,255,255,0.45)';
        ctx.textAlign = 'left';
        ctx.fillText(label, lx + 12, 15);
        lx += ctx.measureText(label).width + 24;
      }

      const hits: HitNode[] = [];
      const zoom = viewportRef.current.zoom;

      for (const edge of edges) {
        const source = nodeMap.get(edgeSource(edge as unknown as Record<string, unknown>));
        const target = nodeMap.get(edgeTarget(edge as unknown as Record<string, unknown>));
        if (!source || !target) continue;
        const s = toScreen(source.x, source.y);
        const t = toScreen(target.x, target.y);
        const linkType = edgeType(edge as unknown as Record<string, unknown>);
        const edgeColor = linkType.includes('THERAPEUTIC')
          ? 'rgba(225, 29, 72, 0.18)'
          : linkType.includes('MECHANISM')
            ? 'rgba(124, 58, 237, 0.18)'
            : linkType.includes('OWNS')
              ? 'rgba(217, 119, 6, 0.25)'
              : 'rgba(248, 200, 6, 0.10)';

        ctx.beginPath();
        ctx.strokeStyle = edgeColor;
        ctx.lineWidth = Math.max(0.6, 0.8 * zoom);
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.stroke();
      }

      for (const node of simNodes) {
        const isCenter = node.entity_id === centerEntityId;
        const isHovered = node.entity_id === hoveredNodeIdRef.current;
        const color = TYPE_COLORS[node.entity_type] ?? '#9b9bab';
        const baseR = isCenter
          ? 8
          : node.entity_type !== 'drug'
            ? 6
            : Math.min(3 + node.edgeCount * 0.5, 6);
        const radius = Math.max(2.5, baseR * zoom);
        const point = toScreen(node.x, node.y);

        if (isCenter) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 6, 0, Math.PI * 2);
          ctx.fillStyle = `${color}12`;
          ctx.fill();
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 3, 0, Math.PI * 2);
          ctx.fillStyle = `${color}20`;
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        if (isHovered) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 3, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(255,255,255,0.75)';
          ctx.lineWidth = 1.3;
          ctx.stroke();
        }
        hits.push({ x: point.x, y: point.y, radius, edgeCount: node.edgeCount, node });

        const showLabel = isCenter || node.entity_type !== 'drug' || node.edgeCount > 2 || displayNodes.length <= 12;
        if (showLabel) {
          const fontSize = isCenter ? 11 : node.entity_type !== 'drug' ? 9 : 8;
          const scaledSize = Math.min(13, Math.max(7, fontSize * Math.max(0.85, zoom)));
          ctx.font = `${isCenter ? '600 ' : ''}${scaledSize}px Inter, sans-serif`;
          ctx.fillStyle = isCenter ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.55)';
          ctx.textAlign = 'center';
          const label = node.label.length > 24 ? `${node.label.slice(0, 22)}..` : node.label;
          ctx.fillText(label, point.x, point.y + radius + 11);
        }
      }
      hitNodesRef.current = hits;
    };

    let iter = 0;
    const maxIter = 180;
    const tick = () => {
      iter += 1;
      draw(true);
      if (iter < maxIter) rafRef.current = requestAnimationFrame(tick);
    };

    drawRef.current = () => draw(false);
    tick();

    return () => {
      cancelAnimationFrame(rafRef.current);
      drawRef.current = () => {};
    };
  }, [nodes, edges, centerEntityId, height, hiddenTypes]);

  if (nodes.length === 0) {
    return (
      <div className="card flex items-center justify-center text-xs text-neutral-400" style={{ height }}>
        No graph data
      </div>
    );
  }

  return (
    <div className="card relative overflow-hidden" style={{ height }}>
      <canvas
        ref={canvasRef}
        tabIndex={0}
        onClick={handleCanvasClick}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onKeyDown={handleKeyDown}
        className={`h-full w-full rounded-lg bg-neutral-900 outline-none focus:ring-2 focus:ring-brand/40 ${dragging ? 'cursor-grabbing' : onNodeClick ? 'cursor-pointer' : 'cursor-grab'}`}
        style={{ touchAction: 'none' }}
      />

      {hoverInfo && (
        <div
          className="pointer-events-none absolute z-20 max-w-[14rem] rounded-md border border-white/20 bg-slate-950/85 px-2 py-1.5 text-[10px] text-white/90 shadow-lg backdrop-blur"
          style={{ left: hoverInfo.x, top: hoverInfo.y }}
        >
          <div className="truncate font-semibold">{hoverInfo.label}</div>
          <div className="mt-0.5 text-white/70">
            {TYPE_LABELS[hoverInfo.entityType] ?? hoverInfo.entityType} · {hoverInfo.edgeCount} links
          </div>
        </div>
      )}

      <div className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-white/20 bg-slate-950/70 px-1.5 py-1 text-[10px] text-white/80 backdrop-blur">
        <button
          type="button"
          onClick={() => zoomByFactor(0.9)}
          className="rounded px-1 py-0.5 hover:bg-white/15"
          aria-label="Zoom out"
        >
          -
        </button>
        <span className="min-w-[3ch] text-center">{zoomPct}%</span>
        <button
          type="button"
          onClick={() => zoomByFactor(1.12)}
          className="rounded px-1 py-0.5 hover:bg-white/15"
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={resetView}
          className="rounded px-1 py-0.5 hover:bg-white/15"
          aria-label="Reset view"
        >
          reset
        </button>
      </div>

      {/* Entity type filters */}
      <div className="absolute left-2 top-2 flex flex-wrap gap-1">
        {Object.entries(TYPE_LABELS).map(([type, label]) => {
          const active = !hiddenTypes.has(type);
          const color = TYPE_COLORS[type] ?? '#9b9bab';
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              className="flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[9px] transition-opacity backdrop-blur"
              style={{
                background: active ? `${color}25` : 'rgba(15,23,42,0.5)',
                color: active ? color : 'rgba(255,255,255,0.35)',
                border: `1px solid ${active ? `${color}40` : 'rgba(255,255,255,0.1)'}`,
                opacity: active ? 1 : 0.6,
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: active ? color : 'rgba(255,255,255,0.3)' }} />
              {label}
            </button>
          );
        })}
      </div>

      {/* Edge type legend */}
      <div className="pointer-events-none absolute bottom-2 right-2 flex flex-wrap gap-x-3 gap-y-0.5 rounded-md border border-white/15 bg-slate-950/60 px-2 py-1 text-[9px] text-white/65 backdrop-blur">
        <span className="flex items-center gap-1"><span className="inline-block h-px w-3" style={{ background: 'rgba(225, 29, 72, 0.5)' }} />Therapeutic</span>
        <span className="flex items-center gap-1"><span className="inline-block h-px w-3" style={{ background: 'rgba(124, 58, 237, 0.5)' }} />Mechanism</span>
        <span className="flex items-center gap-1"><span className="inline-block h-px w-3" style={{ background: 'rgba(217, 119, 6, 0.6)' }} />Ownership</span>
        <span className="flex items-center gap-1"><span className="inline-block h-px w-3" style={{ background: 'rgba(248, 200, 6, 0.3)' }} />Other</span>
      </div>

      <div className="pointer-events-none absolute bottom-2 left-2 rounded-md border border-white/15 bg-slate-950/60 px-2 py-1 text-[10px] text-white/65 backdrop-blur">
        Drag to pan. Wheel or +/- to zoom. Click type badges to filter.
      </div>
    </div>
  );
}
