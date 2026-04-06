import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import type { IntelligenceFeedItem, GraphNode, GraphEdge } from '../../api';
import { api } from '../../api';
import KnowledgeGraph from '../KnowledgeGraph';

/* ── Severity palette ───────────────────────────────── */

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--color-severity-critical)',
  high: 'var(--color-severity-high)',
  medium: 'var(--color-severity-medium)',
  low: 'var(--color-severity-low)',
};

/** CSS custom property value for the pulse animation color */
const PULSE_CSS_COLORS: Record<string, string> = {
  critical: 'rgba(192, 57, 43, 0.4)',
  high: 'rgba(230, 126, 34, 0.4)',
};

/** Raw hex-ish colors for the dot background (non-variable for test assertions) */
const DOT_BG_COLORS: Record<string, string> = {
  critical: '#C0392B',
  high: '#E67E22',
  medium: '#F1C40F',
  low: '#2ECC71',
};

const TIER_INDICATORS: Record<string, string> = {
  T1: '\u2713 T1',
  T2: '\u25D0 T2',
  T3: '\u25CC T3',
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/* ── Action buttons per event type ──────────────────── */

function getActionButtons(item: IntelligenceFeedItem): Array<{
  label: string;
  question: string;
}> {
  const actions: Array<{ label: string; question: string }> = [];

  if (item.primary_entity_name) {
    actions.push({
      label: 'View landscape',
      question: `Show the competitive landscape for ${item.primary_entity_name}`,
    });
    actions.push({
      label: 'Compare',
      question: `Compare ${item.primary_entity_name} with competitors`,
    });
  }

  actions.push({
    label: 'Ask AI',
    question: `Tell me about the impact of ${item.description}`,
  });

  return actions;
}

/* ── Props ──────────────────────────────────────────── */

export interface EventCardProps {
  item: IntelligenceFeedItem;
  onClick: (item: IntelligenceFeedItem) => void;
  onDismiss: (eventId: string) => void;
  onAskInChat?: (question: string) => void;
}

/* ── Inline mini-graph for critical/high ────────────── */

function MiniGraph({ entityName, entityType }: { entityName: string; entityType: string }) {
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [visible, setVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Lazy fetch via IntersectionObserver (graceful fallback for environments without it)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      // Fallback: load immediately if IntersectionObserver is not available
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } },
      { threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    api.traverse(entityType, entityName, 1)
      .then(data => { if (!cancelled) setGraphData(data); })
      .catch(() => { /* Graph endpoint may not be available */ });
    return () => { cancelled = true; };
  }, [visible, entityName, entityType]);

  return (
    <div ref={containerRef} style={{ width: 200, height: 150, borderRadius: '6px', overflow: 'hidden', marginTop: '8px' }}>
      {graphData && graphData.nodes.length > 0 ? (
        <KnowledgeGraph
          nodes={graphData.nodes}
          edges={graphData.edges}
          height={150}
          compact
        />
      ) : visible ? (
        <div style={{
          width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'var(--color-surface-2)', fontSize: '11px', color: 'var(--color-ink-4)',
        }}>
          Loading graph...
        </div>
      ) : null}
    </div>
  );
}

/* ── Digest Card (grouped events) ───────────────────── */

export interface DigestGroup {
  key: string;
  eventType: string;
  entityType: string;
  items: IntelligenceFeedItem[];
  highestSeverity: string;
}

export interface DigestCardProps {
  group: DigestGroup;
  onClick: (item: IntelligenceFeedItem) => void;
  onDismiss: (eventId: string) => void;
  onAskInChat?: (question: string) => void;
}

export function DigestCard({ group, onClick, onDismiss, onAskInChat }: DigestCardProps) {
  const [expanded, setExpanded] = useState(false);
  const severityColor = SEVERITY_COLORS[group.highestSeverity] ?? SEVERITY_COLORS.low;
  const eventLabel = group.eventType.replace(/_/g, ' ');
  const entityLabel = group.entityType.replace(/_/g, ' ');

  return (
    <div
      style={{
        borderLeft: `4px solid ${severityColor}`,
        background: 'var(--color-surface)',
        borderRadius: '6px',
        borderBottom: '1px solid var(--color-line)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          width: '100%', padding: '14px 16px',
          background: 'none', border: 'none', cursor: 'pointer',
          textAlign: 'left', fontFamily: 'var(--font-body)',
        }}
      >
        <ChevronDown
          size={14}
          style={{
            color: 'var(--color-ink-3)', flexShrink: 0,
            transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
            transition: 'transform 0.15s',
          }}
        />
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)', flex: 1 }}>
          {group.items.length} new {eventLabel} events for {entityLabel}
        </span>
        <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
          {group.items.length} event{group.items.length !== 1 ? 's' : ''}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '0 12px 12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {group.items.map(item => (
            <EventCard
              key={item.event_id}
              item={item}
              onClick={onClick}
              onDismiss={onDismiss}
              onAskInChat={onAskInChat}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Digest grouping logic ──────────────────────────── */

const SEVERITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

export function groupEventsForDigest(items: IntelligenceFeedItem[]): DigestGroup[] {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const groups = new Map<string, DigestGroup>();

  for (const item of items) {
    const age = now - new Date(item.created_at).getTime();
    if (age > dayMs) continue; // Only group events within 24 hours

    const entityType = item.primary_entity_type ?? 'unknown';
    const key = `${entityType}::${item.event_type}`;

    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        eventType: item.event_type,
        entityType,
        items: [],
        highestSeverity: item.severity,
      };
      groups.set(key, group);
    }
    group.items.push(item);
    if ((SEVERITY_RANK[item.severity] ?? 0) > (SEVERITY_RANK[group.highestSeverity] ?? 0)) {
      group.highestSeverity = item.severity;
    }
  }

  // Only return groups with 2+ items (singletons stay as regular cards)
  return [...groups.values()].filter(g => g.items.length >= 2);
}

/* ── Main EventCard ─────────────────────────────────── */

export function EventCard({ item, onClick, onDismiss, onAskInChat }: EventCardProps) {
  const severityColor = SEVERITY_COLORS[item.severity] ?? SEVERITY_COLORS.low;
  const tierLabel = TIER_INDICATORS[item.source_tier] ?? item.source_tier;
  const dotBg = DOT_BG_COLORS[item.severity] ?? DOT_BG_COLORS.low;
  const isPulsing = item.severity === 'critical' || item.severity === 'high';
  const showGraph = isPulsing && item.primary_entity_name && item.primary_entity_type;
  const actions = getActionButtons(item);

  const handleActionClick = useCallback((e: React.MouseEvent, question: string) => {
    e.stopPropagation();
    onAskInChat?.(question);
  }, [onAskInChat]);

  return (
    <button
      type="button"
      onClick={() => onClick(item)}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        width: '100%',
        padding: '14px 16px',
        borderLeft: `4px solid ${severityColor}`,
        background: 'var(--color-surface)',
        borderTop: 'none',
        borderRight: 'none',
        borderBottom: '1px solid var(--color-line)',
        borderRadius: '6px',
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: 'var(--font-body)',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-2)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface)'; }}
    >
      {/* Severity pulse dot */}
      <span
        data-testid={`severity-dot-${item.severity}`}
        style={{
          display: 'inline-block',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: dotBg,
          flexShrink: 0,
          marginTop: '5px',
          ...(isPulsing
            ? {
                animation: 'severity-pulse 2s ease-in-out infinite',
                // Use custom property for pulse color
                ['--pulse-color' as string]: PULSE_CSS_COLORS[item.severity] ?? 'rgba(192,57,43,0.4)',
              }
            : {}),
        }}
      />

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Top row: severity + timestamp + source tier */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <span
            style={{
              fontSize: '10px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: severityColor,
            }}
          >
            {item.severity}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
            {relativeTime(item.created_at)}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
            {tierLabel}
          </span>
        </div>

        {/* Title */}
        <div
          style={{
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--color-ink)',
            lineHeight: 1.4,
            marginBottom: '6px',
          }}
        >
          {item.description}
        </div>

        {/* Bottom row: entity pill + impact badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {item.primary_entity_name && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '999px',
                background: entityBackground(item.primary_entity_type),
                color: entityColor(item.primary_entity_type),
              }}
            >
              {item.primary_entity_name}
            </span>
          )}
          {item.impact_count > 0 && (
            <span
              style={{
                fontSize: '11px',
                color: 'var(--color-ink-3)',
                fontWeight: 500,
              }}
            >
              {item.impact_count} affected
            </span>
          )}
        </div>

        {/* Action buttons */}
        {onAskInChat && actions.length > 0 && (
          <div style={{ display: 'flex', gap: '8px', marginTop: '8px', flexWrap: 'wrap' }}>
            {actions.map(action => (
              <span
                key={action.label}
                role="button"
                tabIndex={0}
                onClick={e => handleActionClick(e, action.question)}
                onKeyDown={e => { if (e.key === 'Enter') handleActionClick(e as unknown as React.MouseEvent, action.question); }}
                style={{
                  fontSize: '11px',
                  fontWeight: 500,
                  color: 'var(--color-accent)',
                  cursor: 'pointer',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  fontFamily: 'var(--font-body)',
                  textDecoration: 'none',
                }}
              >
                {action.label}
              </span>
            ))}
          </div>
        )}

        {/* Inline mini-graph for critical/high events with entity */}
        {showGraph && (
          <MiniGraph
            entityName={item.primary_entity_name!}
            entityType={item.primary_entity_type!}
          />
        )}
      </div>

      {/* Dismiss button */}
      <span
        role="button"
        tabIndex={0}
        onClick={e => {
          e.stopPropagation();
          onDismiss(item.event_id);
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') { e.stopPropagation(); onDismiss(item.event_id); }
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '24px',
          height: '24px',
          borderRadius: '6px',
          color: 'var(--color-ink-4)',
          flexShrink: 0,
          cursor: 'pointer',
          transition: 'color 0.15s',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ink-2)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ink-4)'; }}
      >
        <X size={14} />
      </span>
    </button>
  );
}

/* ── Helpers ─────────────────────────────────────────── */

function entityColor(entityType: string | null): string {
  const map: Record<string, string> = {
    drug: 'var(--color-drug)',
    company: 'var(--color-company)',
    trial: 'var(--color-trial)',
    therapeutic_area: 'var(--color-ta)',
    mechanism: 'var(--color-mechanism)',
    literature: 'var(--color-literature)',
  };
  return map[entityType ?? ''] ?? 'var(--color-ink-3)';
}

function entityBackground(entityType: string | null): string {
  const map: Record<string, string> = {
    drug: 'rgba(37, 99, 235, 0.08)',
    company: 'rgba(217, 119, 6, 0.08)',
    trial: 'rgba(13, 148, 136, 0.08)',
    therapeutic_area: 'rgba(225, 29, 72, 0.08)',
    mechanism: 'rgba(124, 58, 237, 0.08)',
    literature: 'rgba(5, 150, 105, 0.08)',
  };
  return map[entityType ?? ''] ?? 'var(--color-surface-2)';
}
