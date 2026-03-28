import { X } from 'lucide-react';
import type { IntelligenceFeedItem } from '../../api';

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--color-severity-critical)',
  high: 'var(--color-severity-high)',
  medium: 'var(--color-severity-medium)',
  low: 'var(--color-severity-low)',
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

interface EventCardProps {
  item: IntelligenceFeedItem;
  onClick: (item: IntelligenceFeedItem) => void;
  onDismiss: (eventId: string) => void;
}

export function EventCard({ item, onClick, onDismiss }: EventCardProps) {
  const severityColor = SEVERITY_COLORS[item.severity] ?? SEVERITY_COLORS.low;
  const tierLabel = TIER_INDICATORS[item.source_tier] ?? item.source_tier;

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
