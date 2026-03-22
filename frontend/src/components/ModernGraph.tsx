import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type GraphNode, type GraphEdge } from '../api';

interface ModernGraphProps {
    nodes: GraphNode[];
    edges: GraphEdge[];
    centerEntityId?: string;
    onNodeClick: (node: GraphNode) => void;
    className?: string;
}

const TYPE_COLORS: Record<string, string> = {
    drug: '#2563eb',       // Blue 600
    company: '#d97706',    // Amber 600
    trial: '#0d9488',      // Teal 600
    therapeutic_area: '#e11d48', // Rose 600
    mechanism: '#7c3aed',  // Violet 600
    literature: '#16a34a', // Green 600
};

const EDGE_COLORS: Record<string, string> = {
    OWNS: '#d97706',            // Amber — ownership
    MANUFACTURES: '#d97706',
    SPONSORS: '#0d9488',        // Teal — sponsorship
    INVESTIGATES: '#2563eb',    // Blue — clinical investigation
    EVIDENCE_FOR: '#16a34a',    // Green — literature evidence
    TARGETS: '#7c3aed',         // Violet — mechanism targeting
    TREATS: '#e11d48',          // Rose — therapeutic
    HAS_SIGNAL: '#dc2626',      // Red — safety signal
    ASSOCIATED_WITH: '#94a3b8', // Grey — generic association
};

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

        const simNodes = nodes.map((n) => ({
            ...n,
            x: cx + (Math.random() - 0.5) * 200,
            y: cy + (Math.random() - 0.5) * 200,
            vx: 0,
            vy: 0,
            radius: n.entity_id === centerEntityId ? 16 : 8
        }));

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
            ctx.clearRect(0, 0, w, h);

            // Edges — only draw visible (non-hidden) edges
            ctx.lineWidth = 1;
            for (const edge of visibleEdges) {
                const sId = (edge as any).source_id || (edge as any).source;
                const tId = (edge as any).target_id || (edge as any).target;
                const s = nodeMap.get(sId);
                const t = nodeMap.get(tId);

                if (s && t) {
                    const linkType = (edge as any).link_type || '';
                    const edgeColor = EDGE_COLORS[linkType] || '#d4d4d8';
                    const conf = (edge as any).confidence ?? 0.5;
                    ctx.beginPath();
                    ctx.moveTo(s.x, s.y);
                    ctx.lineTo(t.x, t.y);
                    ctx.strokeStyle = edgeColor;
                    ctx.globalAlpha = 0.3 + conf * 0.5; // Higher confidence = more visible
                    ctx.stroke();
                    ctx.globalAlpha = 1;
                }
            }

            // Nodes
            for (const node of simNodes) {
                const isCenter = node.entity_id === centerEntityId;
                const isHover = node.entity_id === hoverNodeId;

                ctx.beginPath();
                const r = isCenter ? 20 : (isHover ? 10 : 8);
                ctx.arc(node.x, node.y, r, 0, Math.PI * 2);

                // Fill
                ctx.fillStyle = TYPE_COLORS[node.entity_type] || '#64748b';
                ctx.fill();

                // Border (White ring)
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Label
                if (isCenter || isHover || nodes.length < 20) {
                    ctx.beginPath();
                    ctx.font = isCenter ? 'bold 12px Inter' : '10px Inter';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = '#0f172a'; // Slate 900

                    // Background for text
                    const textWidth = ctx.measureText(node.label).width;
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                    ctx.roundRect(node.x - textWidth / 2 - 4, node.y + r + 4, textWidth + 8, 16, 4);
                    ctx.fill();

                    ctx.fillStyle = '#0f172a';
                    ctx.fillText(node.label, node.x, node.y + r + 12);
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
        <div ref={containerRef} className={`relative w-full h-full bg-slate-50 overflow-hidden ${className}`}>
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
                        background: 'rgba(255, 255, 255, 0.92)',
                        backdropFilter: 'blur(8px)',
                        border: '1px solid var(--color-line, #e2e8f0)',
                        fontSize: '11px',
                        maxWidth: 'min(90%, 420px)',
                        zIndex: 10,
                    }}
                >
                    {presentEdgeTypes.map((linkType) => {
                        const isHidden = hiddenEdgeTypes.has(linkType);
                        const dotColor = EDGE_COLORS[linkType] || '#94a3b8';
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
                                    color: isHidden ? 'var(--color-ink-4, #a1a1aa)' : 'var(--color-ink-2, #374151)',
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
                                        background: isHidden ? 'var(--color-ink-4, #a1a1aa)' : dotColor,
                                        flexShrink: 0,
                                    }}
                                />
                                {linkType.replace(/_/g, ' ')}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
