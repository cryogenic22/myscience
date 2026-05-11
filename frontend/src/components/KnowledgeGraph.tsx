/**
 * KnowledgeGraph — Unified graph renderer for Market Zero.
 *
 * Replaces both GraphMini (search panel) and ModernGraph (graph explorer)
 * with a single canvas-based force-directed graph.
 *
 * Features:
 * - Dark canvas with entity-coloured nodes and link-type-coloured edges
 * - Full pan/zoom (pointer drag, wheel, keyboard arrows/+/-/0)
 * - 180-frame physics simulation then stops (no infinite RAF)
 * - Degree-based node sizing with optional influence scoring
 * - Hover tooltip with entity metadata
 * - Entity type toggle pills and edge category legend
 * - Confidence-based edge opacity and width
 * - Path highlight mode
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { GraphEdge, GraphNode } from '../api';
import { ENTITY_TYPE_LABELS, LINK_TYPE_LABELS } from '../brand';
import {
  NODE_COLORS as ENTITY_TYPE_COLORS,
  EDGE_COLORS as LINK_TYPE_COLORS,
  EDGE_LABELS,
  NODE_TYPE_LABELS,
  GRAPH_BG,
  GRAPH_TEXT,
} from './graph/graph-constants';

// Edge categories for the legend grouping
const EDGE_CATEGORIES: Record<string, { label: string; color: string; types: string[] }> = {
  ownership: { label: 'Ownership', color: '#f59e0b', types: ['OWNS', 'MANUFACTURES', 'SPONSORS'] },
  research: { label: 'Research', color: '#14b8a6', types: ['INVESTIGATES', 'EVIDENCE_FOR', 'HAS_OUTCOME', 'LED_BY', 'AUTHORED_BY'] },
  science: { label: 'Science', color: '#a78bfa', types: ['TARGETS_MECHANISM', 'IN_THERAPEUTIC_AREA'] },
  regulatory: { label: 'Regulatory', color: '#64748b', types: ['HAS_PATENT', 'HAS_MILESTONE', 'HAS_LABEL'] },
  safety: { label: 'Safety', color: '#ef4444', types: ['HAS_ADVERSE_EVENT', 'SHORTAGE_AFFECTS', 'COMPETES_WITH'] },
};

// ── Props ─────────────────────────────────────────────────────

export interface KnowledgeGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  centerEntityId?: string;
  /** Optional set of edge IDs (source-target pairs) forming a highlighted path */
  highlightPath?: Set<string>;
  height?: number;
  onNodeClick?: (node: GraphNode) => void;
  /** Right-click context menu on a node — receives the node and screen position */
  onNodeContextMenu?: (node: GraphNode, position: { x: number; y: number }) => void;
  /** Compact mode hides the edge legend and instruction hint */
  compact?: boolean;
  className?: string;
}

// ── Internal types ────────────────────────────────────────────

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

// ── Helpers ───────────────────────────────────────────────────

function edgeSource(e: Record<string, unknown>): string {
  return String(e.source_id ?? e.source ?? '');
}

function edgeTarget(e: Record<string, unknown>): string {
  return String(e.target_id ?? e.target ?? '');
}

function edgeLinkType(e: Record<string, unknown>): string {
  return String(e.link_type ?? e.type ?? '');
}

function edgeConfidence(e: Record<string, unknown>): number {
  const c = e.confidence;
  return typeof c === 'number' ? c : 1.0;
}

function clampZoom(raw: number): number {
  return Math.max(0.4, Math.min(3.0, raw));
}

function pathKey(sourceId: string, targetId: string): string {
  return sourceId < targetId ? `${sourceId}:${targetId}` : `${targetId}:${sourceId}`;
}

// ── Component ─────────────────────────────────────────────────

export default function KnowledgeGraph({
  nodes,
  edges,
  centerEntityId,
  highlightPath,
  height = 400,
  onNodeClick,
  onNodeContextMenu,
  compact = false,
  className = '',
}: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const drawRef = useRef<() => void>(() => {});
  const viewportRef = useRef<Viewport>({ zoom: 1, offsetX: 0, offsetY: 0 });
  const hitNodesRef = useRef<HitNode[]>([]);
  const hoveredNodeIdRef = useRef<string | null>(null);
  const dragRef = useRef<{
    dragging: boolean;
    pointerId: number | null;
    lastX: number;
    lastY: number;
  }>({ dragging: false, pointerId: null, lastX: 0, lastY: 0 });

  const [zoomPct, setZoomPct] = useState(100);
  const [dragging, setDragging] = useState(false);
  const [hoverInfo, setHoverInfo] = useState<{
    x: number;
    y: number;
    label: string;
    entityType: string;
    edgeCount: number;
    confidence?: number;
  } | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [hiddenEdgeCategories, setHiddenEdgeCategories] = useState<Set<string>>(new Set());

  // Build set of hidden link types from hidden edge categories
  const hiddenLinkTypes = new Set<string>();
  for (const [catKey, cat] of Object.entries(EDGE_CATEGORIES)) {
    if (hiddenEdgeCategories.has(catKey)) {
      for (const t of cat.types) hiddenLinkTypes.add(t);
    }
  }

  const toggleType = useCallback((type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const toggleEdgeCategory = useCallback((catKey: string) => {
    setHiddenEdgeCategories((prev) => {
      const next = new Set(prev);
      if (next.has(catKey)) next.delete(catKey);
      else next.add(catKey);
      return next;
    });
  }, []);

  // ── Hit testing ───────────────────────────────────────────

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

  // ── Pan / Zoom ────────────────────────────────────────────

  const panBy = useCallback((dx: number, dy: number) => {
    const v = viewportRef.current;
    v.offsetX += dx;
    v.offsetY += dy;
    drawRef.current();
  }, []);

  const zoomByFactor = useCallback(
    (factor: number, anchor?: { x: number; y: number }) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const ax = anchor?.x ?? rect.width / 2;
      const ay = anchor?.y ?? rect.height / 2;
      const v = viewportRef.current;
      const nextZoom = clampZoom(v.zoom * factor);
      const worldX = (ax - v.offsetX) / v.zoom;
      const worldY = (ay - v.offsetY) / v.zoom;
      v.zoom = nextZoom;
      v.offsetX = ax - worldX * nextZoom;
      v.offsetY = ay - worldY * nextZoom;
      setZoomPct(Math.round(nextZoom * 100));
      drawRef.current();
    },
    [],
  );

  const resetView = useCallback(() => {
    viewportRef.current = { zoom: 1, offsetX: 0, offsetY: 0 };
    setZoomPct(100);
    drawRef.current();
  }, []);

  // ── Event handlers ────────────────────────────────────────

  const handleCanvasClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onNodeClick) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const hit = pickHitNode(event.clientX - rect.left, event.clientY - rect.top);
      if (hit) onNodeClick(hit.node);
    },
    [onNodeClick, pickHitNode],
  );

  const handleContextMenu = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onNodeContextMenu) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const hit = pickHitNode(event.clientX - rect.left, event.clientY - rect.top);
      if (hit) {
        event.preventDefault();
        onNodeContextMenu(hit.node, { x: event.clientX, y: event.clientY });
      }
    },
    [onNodeContextMenu, pickHitNode],
  );

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

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const drag = dragRef.current;
      if (drag.dragging && drag.pointerId === event.pointerId) {
        panBy(event.clientX - drag.lastX, event.clientY - drag.lastY);
        drag.lastX = event.clientX;
        drag.lastY = event.clientY;
        return;
      }
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const hit = pickHitNode(x, y);
      const nextId = hit?.node.entity_id ?? null;
      if (hoveredNodeIdRef.current !== nextId) {
        hoveredNodeIdRef.current = nextId;
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
    },
    [panBy, pickHitNode, hoverInfo],
  );

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

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLCanvasElement>) => {
      event.preventDefault();
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      zoomByFactor(event.deltaY > 0 ? 0.9 : 1.12, {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    },
    [zoomByFactor],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLCanvasElement>) => {
      const key = event.key;
      if (key === 'ArrowLeft') { event.preventDefault(); panBy(-22, 0); return; }
      if (key === 'ArrowRight') { event.preventDefault(); panBy(22, 0); return; }
      if (key === 'ArrowUp') { event.preventDefault(); panBy(0, -22); return; }
      if (key === 'ArrowDown') { event.preventDefault(); panBy(0, 22); return; }
      if (key === '+' || key === '=') { event.preventDefault(); zoomByFactor(1.12); return; }
      if (key === '-' || key === '_') { event.preventDefault(); zoomByFactor(0.9); return; }
      if (key === '0') { event.preventDefault(); resetView(); }
    },
    [panBy, zoomByFactor, resetView],
  );

  // ── Main render effect ────────────────────────────────────

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
    const cx = w / 2;
    const cy = h / 2;

    // Count edges per node
    const edgeCounts = new Map<string, number>();
    for (const e of edges) {
      const s = edgeSource(e as unknown as Record<string, unknown>);
      const t = edgeTarget(e as unknown as Record<string, unknown>);
      edgeCounts.set(s, (edgeCounts.get(s) ?? 0) + 1);
      edgeCounts.set(t, (edgeCounts.get(t) ?? 0) + 1);
    }

    // Filter out hidden node types, cap at 60 nodes
    const visibleNodes = nodes.filter((n) => !hiddenTypes.has(n.entity_type));
    const cappedNodes = visibleNodes.slice(0, 60);

    // Initialise simulation nodes
    const simNodes: SimNode[] = cappedNodes.map((node, index) => {
      const isCenter = node.entity_id === centerEntityId;
      const angle = (2 * Math.PI * index) / Math.max(cappedNodes.length, 1);
      const baseR = node.entity_type === 'drug' ? 55 + Math.random() * 30 : 85 + Math.random() * 35;
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

    const nodeMap = new Map(simNodes.map((n) => [n.entity_id, n]));
    const presentTypes = new Set(simNodes.map((n) => n.entity_type));

    // Viewport transform
    const toScreen = (worldX: number, worldY: number) => {
      const v = viewportRef.current;
      return { x: worldX * v.zoom + v.offsetX, y: worldY * v.zoom + v.offsetY };
    };

    // ── Draw function ─────────────────────────────────────

    const draw = (advancePhysics: boolean) => {
      if (advancePhysics) {
        // Centre gravity + repulsion + edge springs
        for (const node of simNodes) {
          if (node.fx !== undefined) {
            node.x = node.fx;
            node.y = node.fy!;
            continue;
          }
          // Centre gravity
          node.vx += (cx - node.x) * 0.002;
          node.vy += (cy - node.y) * 0.002;
          // Node repulsion
          for (const other of simNodes) {
            if (node === other) continue;
            const dx = node.x - other.x;
            const dy = node.y - other.y;
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
            const force = 300 / (dist * dist);
            node.vx += (dx / dist) * force;
            node.vy += (dy / dist) * force;
          }
          // Edge springs
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
          // Damping
          node.vx *= 0.82;
          node.vy *= 0.82;
          node.x = Math.max(30, Math.min(w - 30, node.x + node.vx));
          node.y = Math.max(20, Math.min(h - 20, node.y + node.vy));
        }
      }

      ctx.clearRect(0, 0, w, h);
      const zoom = viewportRef.current.zoom;
      const hits: HitNode[] = [];

      // ── Draw edges ────────────────────────────────────
      for (const edge of edges) {
        const eRaw = edge as unknown as Record<string, unknown>;
        const lt = edgeLinkType(eRaw);
        if (hiddenLinkTypes.has(lt)) continue;

        const source = nodeMap.get(edgeSource(eRaw));
        const target = nodeMap.get(edgeTarget(eRaw));
        if (!source || !target) continue;

        const s = toScreen(source.x, source.y);
        const t = toScreen(target.x, target.y);
        const conf = edgeConfidence(eRaw);

        // Path highlight mode
        const isOnPath = highlightPath
          ? highlightPath.has(pathKey(edgeSource(eRaw), edgeTarget(eRaw)))
          : false;

        const baseColor = LINK_TYPE_COLORS[lt] ?? '#94a3b8';
        const opacity = highlightPath
          ? (isOnPath ? 0.9 : 0.08)
          : 0.15 + conf * 0.45;
        const lineWidth = highlightPath
          ? (isOnPath ? 2.5 : 0.4)
          : Math.max(0.5, (0.5 + conf * 2.0) * Math.max(0.7, zoom));

        ctx.beginPath();
        ctx.strokeStyle = baseColor;
        ctx.globalAlpha = opacity;
        ctx.lineWidth = lineWidth;

        // Dashed line for competition edges
        if (lt === 'COMPETES_WITH' || lt === 'PATENT_BLOCKS') {
          ctx.setLineDash([4, 3]);
        } else {
          ctx.setLineDash([]);
        }

        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.stroke();
        ctx.globalAlpha = 1.0;
        ctx.setLineDash([]);
      }

      // ── Draw nodes ────────────────────────────────────
      for (const node of simNodes) {
        const isCenter = node.entity_id === centerEntityId;
        const isHovered = node.entity_id === hoveredNodeIdRef.current;
        const color = ENTITY_TYPE_COLORS[node.entity_type] ?? ENTITY_TYPE_COLORS.unknown ?? '#6b7280';

        // Degree-based sizing: base 4, max ~14
        const degreeBonus = Math.min(node.edgeCount * 0.6, 10);
        const baseR = isCenter ? 10 : 4 + degreeBonus;
        const radius = Math.max(2.5, baseR * Math.max(0.7, zoom));
        const point = toScreen(node.x, node.y);

        // Centre entity glow
        if (isCenter) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 6, 0, Math.PI * 2);
          ctx.fillStyle = `${color}15`;
          ctx.fill();
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 3, 0, Math.PI * 2);
          ctx.fillStyle = `${color}25`;
          ctx.fill();
        }

        // Node circle
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Hover ring
        if (isHovered) {
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 3, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(255,255,255,0.75)';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        hits.push({ x: point.x, y: point.y, radius, edgeCount: node.edgeCount, node });

        // Labels: always for centre, non-drug types, high-degree, or small graphs
        const showLabel =
          isCenter ||
          isHovered ||
          node.entity_type !== 'drug' ||
          node.edgeCount > 3 ||
          cappedNodes.length <= 15;

        if (showLabel) {
          const fontSize = isCenter ? 11 : node.entity_type !== 'drug' ? 9.5 : 8;
          const scaledSize = Math.min(14, Math.max(7, fontSize * Math.max(0.85, zoom)));
          ctx.font = `${isCenter ? '600 ' : ''}${scaledSize}px "DM Sans", Inter, sans-serif`;
          ctx.fillStyle = isCenter
            ? 'rgba(255,255,255,0.88)'
            : isHovered
              ? 'rgba(255,255,255,0.8)'
              : 'rgba(255,255,255,0.52)';
          ctx.textAlign = 'center';
          const label = node.label.length > 26 ? `${node.label.slice(0, 24)}..` : node.label;
          ctx.fillText(label, point.x, point.y + radius + 12);
        }
      }

      hitNodesRef.current = hits;
    };

    // ── Physics simulation (180 frames then stop) ────────
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, centerEntityId, height, hiddenTypes, highlightPath]);

  // ── Empty state ───────────────────────────────────────────

  if (nodes.length === 0) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg text-xs ${className}`}
        style={{
          height,
          background: 'var(--color-ink, #0f172a)',
          color: 'rgba(255,255,255,0.4)',
        }}
      >
        No graph data
      </div>
    );
  }

  // ── Derive present entity types and edge categories ────────

  const presentEntityTypes = new Set(nodes.map((n) => n.entity_type));
  const presentEdgeCats: string[] = [];
  for (const [catKey, cat] of Object.entries(EDGE_CATEGORIES)) {
    if (cat.types.some((t) => edges.some((e) => (e as any).link_type === t))) {
      presentEdgeCats.push(catKey);
    }
  }

  return (
    <div className={`relative overflow-hidden rounded-lg ${className}`} style={{ height }}>
      <canvas
        ref={canvasRef}
        tabIndex={0}
        onClick={handleCanvasClick}
        onContextMenu={handleContextMenu}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onKeyDown={handleKeyDown}
        className={`h-full w-full outline-none focus:ring-2 focus:ring-blue-500/30`}
        style={{
          touchAction: 'none',
          background: '#0f172a',
          cursor: dragging ? 'grabbing' : onNodeClick ? 'pointer' : 'grab',
          borderRadius: 'inherit',
        }}
      />

      {/* Hover tooltip */}
      {hoverInfo && (
        <div
          className="pointer-events-none absolute z-20 max-w-[14rem] rounded-md shadow-lg backdrop-blur"
          style={{
            padding: '6px 10px',
            left: hoverInfo.x,
            top: hoverInfo.y,
            background: 'rgba(2, 6, 23, 0.88)',
            border: '1px solid rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.92)',
            fontSize: '11px',
          }}
        >
          <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {hoverInfo.label}
          </div>
          <div style={{ marginTop: 2, color: 'rgba(255,255,255,0.6)', fontSize: '10px' }}>
            {ENTITY_TYPE_LABELS[hoverInfo.entityType] ?? hoverInfo.entityType} · {hoverInfo.edgeCount} connections
          </div>
        </div>
      )}

      {/* Zoom controls — top right */}
      <div
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md backdrop-blur"
        style={{
          padding: '3px 6px',
          background: 'rgba(2, 6, 23, 0.7)',
          border: '1px solid rgba(255,255,255,0.15)',
          color: 'rgba(255,255,255,0.8)',
          fontSize: '10px',
        }}
      >
        <button
          type="button"
          onClick={() => zoomByFactor(0.9)}
          className="rounded hover:bg-surface/15"
          style={{ padding: '2px 5px' }}
          aria-label="Zoom out"
        >
          -
        </button>
        <span style={{ minWidth: '3ch', textAlign: 'center' }}>{zoomPct}%</span>
        <button
          type="button"
          onClick={() => zoomByFactor(1.12)}
          className="rounded hover:bg-surface/15"
          style={{ padding: '2px 5px' }}
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={resetView}
          className="rounded hover:bg-surface/15"
          style={{ padding: '2px 5px' }}
          aria-label="Reset view"
        >
          reset
        </button>
      </div>

      {/* Entity type toggle pills — top left */}
      <div className="absolute left-2 top-2 flex flex-wrap gap-1" style={{ maxWidth: '70%' }}>
        {[...presentEntityTypes].map((type) => {
          const active = !hiddenTypes.has(type);
          const color = ENTITY_TYPE_COLORS[type] ?? '#6b7280';
          const label = ENTITY_TYPE_LABELS[type] ?? type;
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              className="flex items-center gap-1 rounded-sm backdrop-blur transition-opacity"
              style={{
                padding: '2px 6px',
                fontSize: '9px',
                background: active ? `${color}22` : 'rgba(15,23,42,0.5)',
                color: active ? color : 'rgba(255,255,255,0.3)',
                border: `1px solid ${active ? `${color}40` : 'rgba(255,255,255,0.08)'}`,
                opacity: active ? 1 : 0.55,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: active ? color : 'rgba(255,255,255,0.25)',
                }}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Edge category legend — bottom right */}
      {!compact && presentEdgeCats.length > 0 && (
        <div
          className="absolute bottom-2 right-2 flex flex-wrap gap-x-2 gap-y-1 rounded-md backdrop-blur"
          style={{
            padding: '4px 8px',
            background: 'rgba(2, 6, 23, 0.65)',
            border: '1px solid rgba(255,255,255,0.12)',
            fontSize: '9px',
            color: 'rgba(255,255,255,0.6)',
          }}
        >
          {presentEdgeCats.map((catKey) => {
            const cat = EDGE_CATEGORIES[catKey];
            const active = !hiddenEdgeCategories.has(catKey);
            return (
              <button
                key={catKey}
                type="button"
                onClick={() => toggleEdgeCategory(catKey)}
                className="flex items-center gap-1 transition-opacity"
                style={{ opacity: active ? 1 : 0.4, cursor: 'pointer', background: 'none', border: 'none', color: 'inherit', padding: 0, fontSize: 'inherit' }}
              >
                <span
                  style={{
                    display: 'inline-block',
                    width: 12,
                    height: 2,
                    background: active ? cat.color : 'rgba(255,255,255,0.2)',
                    borderRadius: 1,
                  }}
                />
                {cat.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Instruction hint — bottom left */}
      {!compact && (
        <div
          className="pointer-events-none absolute bottom-2 left-2 rounded-md backdrop-blur"
          style={{
            padding: '3px 8px',
            background: 'rgba(2, 6, 23, 0.6)',
            border: '1px solid rgba(255,255,255,0.1)',
            fontSize: '10px',
            color: 'rgba(255,255,255,0.45)',
          }}
        >
          Drag to pan · Scroll to zoom · Click badges to filter
        </div>
      )}
    </div>
  );
}
