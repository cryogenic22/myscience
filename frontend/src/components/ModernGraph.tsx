import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type GraphNode, type GraphEdge } from '../api';
import { NODE_COLORS, EDGE_COLORS, EDGE_LABELS, GRAPH_BG, GRAPH_TEXT } from './graph/graph-constants';

interface ModernGraphProps {
    nodes: GraphNode[];
    edges: GraphEdge[];
    centerEntityId?: string;
    onNodeClick: (node: GraphNode) => void;
    className?: string;
}

export default function ModernGraph({ nodes, edges, centerEntityId, onNodeClick, className = '' }: ModernGraphProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [hoverNodeId, setHoverNodeId] = useState<string | null>(null);
    const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<Set<string>>(new Set());

    // Derive unique edge types present in current graph
    const presentEdgeTypes = useMemo(() => {
        const types = new Set<string>();
        for (const edge of edges) {
            const linkType = (edge as any).link_type || '';
            if (linkType) types.add(linkType);
        }
        return [...types].sort((a, b) => a.localeCompare(b));
    }, [edges]);

    // Filter edges by hidden types
    const visibleEdges = useMemo(
        () => edges.filter((edge) => !hiddenEdgeTypes.has((edge as any).link_type || '')),
        [edges, hiddenEdgeTypes],
    );

    const toggleEdgeType = useCallback((linkType: string) => {
        setHiddenEdgeTypes((prev) => {
            const next = new Set(prev);
            if (next.has(linkType)) {
                next.delete(linkType);
            } else {
                next.add(linkType);
            }
            return next;
        });
    }, []);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !nodes.length) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Responsive Sizing
        const resize = () => {
            const parent = containerRef.current;
            if (parent) {
                const { width, height } = parent.getBoundingClientRect();
                const dpr = window.devicePixelRatio || 1;
                canvas.width = width * dpr;
                canvas.height = height * dpr;
                ctx.scale(dpr, dpr);
                canvas.style.width = `${width}px`;
                canvas.style.height = `${height}px`;
            }
        };
        resize();
        window.addEventListener('resize', resize);

        // Initial Layout Calculation
        // Simple force-directed layout
        const width = canvas.width / (window.devicePixelRatio || 1);
        const height = canvas.height / (window.devicePixelRatio || 1);
        const cx = width / 2;
        const cy = height / 2;

        // Build degree map for node sizing
        const degreeMap = new Map<string, number>();
        for (const edge of edges) {
            const sId = (edge as any).source_id || (edge as any).source;
            const tId = (edge as any).target_id || (edge as any).target;
            degreeMap.set(sId, (degreeMap.get(sId) ?? 0) + 1);
            degreeMap.set(tId, (degreeMap.get(tId) ?? 0) + 1);
        }

        const simNodes = nodes.map((n) => {
            const degree = degreeMap.get(n.entity_id) ?? 0;
            const isCenter = n.entity_id === centerEntityId;
            let radius = 7; // default
            if (isCenter) radius = 20;
            else if (degree >= 5) radius = 12;
            else if (degree >= 3) radius = 9;
            return {
                ...n,
                x: cx + (Math.random() - 0.5) * 200,
                y: cy + (Math.random() - 0.5) * 200,
                vx: 0,
                vy: 0,
                radius,
                degree,
            };
        });

        const nodeMap = new Map(simNodes.map(n => [n.entity_id, n]));

        let animationFrameId: number;

        const render = () => {
            // Physics Tick
            for (const node of simNodes) {
                // Center gravity
                node.vx += (cx - node.x) * 0.005;
                node.vy += (cy - node.y) * 0.005;

                // Repulsion
                for (const other of simNodes) {
                    if (node === other) continue;
                    const dx = node.x - other.x;
                    const dy = node.y - other.y;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    if (dist < 100) {
                        const force = 50 / (dist * dist);
                        node.vx += (dx / dist) * force;
                        node.vy += (dy / dist) * force;
                    }
                }

                // Edge springs
                for (const edge of edges) {
                    // Normalize ID access
                    const sourceId = (edge as any).source_id || (edge as any).source;
                    const targetId = (edge as any).target_id || (edge as any).target;

                    if (node.entity_id === sourceId) {
                        const target = nodeMap.get(targetId);
                        if (target) {
                            const dx = target.x - node.x;
                            const dy = target.y - node.y;
                            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                            const force = (dist - 100) * 0.002;
                            node.vx += (dx / dist) * force;
                            node.vy += (dy / dist) * force;
                        }
                    }
                }

                // Friction
                node.vx *= 0.9;
                node.vy *= 0.9;
                node.x += node.vx;
                node.y += node.vy;
            }

            // Draw
            const w = canvas.width / (window.devicePixelRatio || 1);
            const h = canvas.height / (window.devicePixelRatio || 1);
            ctx.fillStyle = GRAPH_BG;
            ctx.fillRect(0, 0, w, h);

            // Edges — only draw visible (non-hidden) edges
            for (const edge of visibleEdges) {
                const sId = (edge as any).source_id || (edge as any).source;
                const tId = (edge as any).target_id || (edge as any).target;
                const s = nodeMap.get(sId);
                const t = nodeMap.get(tId);

                if (s && t) {
                    const linkType = (edge as any).link_type || '';
                    const edgeColor = EDGE_COLORS[linkType] || '#64748b';
                    const conf = (edge as any).confidence ?? 0.5;
                    ctx.beginPath();
                    ctx.moveTo(s.x, s.y);
                    ctx.lineTo(t.x, t.y);
                    ctx.strokeStyle = edgeColor;
                    ctx.lineWidth = 0.8 + conf * 1.5;
                    ctx.globalAlpha = Math.max(0.4, 0.3 + conf * 0.5);
                    ctx.stroke();
                    ctx.globalAlpha = 1;
                }
            }

            // Nodes
            for (const node of simNodes) {
                const isCenter = node.entity_id === centerEntityId;
                const isHover = node.entity_id === hoverNodeId;

                // Degree-based radius with hover override
                const r = isHover ? Math.max(node.radius, 14) : node.radius;

                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, Math.PI * 2);

                // Fill
                ctx.fillStyle = NODE_COLORS[node.entity_type] || NODE_COLORS.unknown;
                ctx.fill();

                // Border (White ring — slightly subtler on dark bg)
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
                ctx.lineWidth = isCenter ? 2.5 : 1.5;
                ctx.stroke();

                // Label — show for: center, hovered, high-degree (>=3), non-drug types, or small graphs
                const showLabel = isCenter
                    || isHover
                    || node.degree >= 3
                    || (node.entity_type !== 'drug' && node.entity_type !== 'literature')
                    || nodes.length < 20;

                if (showLabel) {
                    const rawLabel = node.label.length > 25 ? `${node.label.slice(0, 23)}...` : node.label;
                    ctx.font = isCenter ? 'bold 12px Inter, sans-serif' : '10px Inter, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';

                    // Semi-transparent dark pill behind text for legibility on dark bg
                    const textWidth = ctx.measureText(rawLabel).width;
                    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
                    ctx.beginPath();
                    ctx.roundRect(node.x - textWidth / 2 - 4, node.y + r + 3, textWidth + 8, 16, 4);
                    ctx.fill();

                    ctx.fillStyle = isCenter ? GRAPH_TEXT : 'rgba(226, 232, 240, 0.8)';
                    ctx.fillText(rawLabel, node.x, node.y + r + 11);
                }
            }

            animationFrameId = requestAnimationFrame(render);
        };

        render();

        // Interaction Handlers
        const handleMouseMove = (e: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            // Simple hit test
            let hitId: string | null = null;
            for (const node of simNodes) {
                const dx = x - node.x;
                const dy = y - node.y;
                if (dx * dx + dy * dy < 20 * 20) { // 20px hit radius
                    hitId = node.entity_id;
                    break;
                }
            }
            setHoverNodeId(hitId);
            canvas.style.cursor = hitId ? 'pointer' : 'default';
        };

        const handleClick = (e: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            for (const node of simNodes) {
                const dx = x - node.x;
                const dy = y - node.y;
                if (dx * dx + dy * dy < 20 * 20) {
                    onNodeClick(node);
                    break;
                }
            }
        };

        canvas.addEventListener('mousemove', handleMouseMove);
        canvas.addEventListener('click', handleClick);

        return () => {
            window.removeEventListener('resize', resize);
            canvas.removeEventListener('mousemove', handleMouseMove);
            canvas.removeEventListener('click', handleClick);
            cancelAnimationFrame(animationFrameId);
        };
    }, [nodes, edges, visibleEdges, centerEntityId, onNodeClick]);

    return (
        <div ref={containerRef} className={`relative w-full h-full overflow-hidden ${className}`} style={{ background: GRAPH_BG }}>
            <canvas ref={canvasRef} className="block" />
            {presentEdgeTypes.length > 0 && (
                <div
                    style={{
                        position: 'absolute',
                        bottom: '12px',
                        left: '12px',
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: '4px 12px',
                        padding: '8px 12px',
                        borderRadius: '8px',
                        background: 'rgba(15, 23, 42, 0.85)',
                        backdropFilter: 'blur(8px)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        fontSize: '11px',
                        maxWidth: 'min(90%, 480px)',
                        zIndex: 10,
                    }}
                >
                    {presentEdgeTypes.map((linkType) => {
                        const isHidden = hiddenEdgeTypes.has(linkType);
                        const dotColor = EDGE_COLORS[linkType] || '#64748b';
                        const label = EDGE_LABELS[linkType] || linkType.replace(/_/g, ' ');
                        return (
                            <button
                                key={linkType}
                                type="button"
                                onClick={() => toggleEdgeType(linkType)}
                                title={isHidden ? `Show ${linkType} edges` : `Hide ${linkType} edges`}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '5px',
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '2px 4px',
                                    borderRadius: '4px',
                                    color: isHidden ? 'rgba(148, 163, 184, 0.5)' : 'rgba(226, 232, 240, 0.85)',
                                    opacity: isHidden ? 0.5 : 1,
                                    fontFamily: 'inherit',
                                    fontSize: '11px',
                                    lineHeight: 1,
                                    textDecoration: isHidden ? 'line-through' : 'none',
                                    transition: 'opacity 0.15s ease',
                                }}
                            >
                                <span
                                    style={{
                                        display: 'inline-block',
                                        width: '8px',
                                        height: '8px',
                                        borderRadius: '50%',
                                        background: isHidden ? 'rgba(148, 163, 184, 0.4)' : dotColor,
                                        flexShrink: 0,
                                    }}
                                />
                                {label}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
