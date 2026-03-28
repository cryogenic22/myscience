import { useCallback, useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Drawer } from '../ui/Drawer';
import type { IntelligenceFeedItem } from '../../api';
import { api } from '../../api';

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--color-severity-critical)',
  high: 'var(--color-severity-high)',
  medium: 'var(--color-severity-medium)',
  low: 'var(--color-severity-low)',
};

const TRUST_COLORS: Record<string, string> = {
  verified: 'var(--color-trust-verified)',
  pending: 'var(--color-trust-pending)',
  unverified: 'var(--color-trust-unverified)',
};

function trustLabel(score: number): { text: string; color: string } {
  if (score >= 0.8) return { text: 'Verified', color: TRUST_COLORS.verified };
  if (score >= 0.5) return { text: 'Pending', color: TRUST_COLORS.pending };
  return { text: 'Unverified', color: TRUST_COLORS.unverified };
}

interface EventDetailDrawerProps {
  item: IntelligenceFeedItem | null;
  onClose: () => void;
  onDismiss: (eventId: string) => void;
}

export function EventDetailDrawer({ item, onClose, onDismiss }: EventDetailDrawerProps) {
  const [detail, setDetail] = useState<{
    event: Record<string, unknown>;
    assessments: Record<string, unknown>[];
  } | null>(null);

  useEffect(() => {
    if (!item) { setDetail(null); return; }
    let cancelled = false;
    api.intelligenceEventDetail(item.event_id)
      .then(d => { if (!cancelled) setDetail(d); })
      .catch(() => { /* Endpoint may not exist yet */ });
    return () => { cancelled = true; };
  }, [item]);

  const handleDismiss = useCallback(() => {
    if (!item) return;
    onDismiss(item.event_id);
    onClose();
  }, [item, onDismiss, onClose]);

  if (!item) return null;

  const severityColor = SEVERITY_COLORS[item.severity] ?? SEVERITY_COLORS.low;
  const trust = trustLabel(item.trust_score);

  // Extract affected entities from assessments
  const affectedEntities: Array<{name: string; type: string; direction: string}> = [];
  if (detail?.assessments) {
    for (const a of detail.assessments) {
      if (a.entity_name && a.entity_type) {
        affectedEntities.push({
          name: String(a.entity_name),
          type: String(a.entity_type),
          direction: String(a.impact_direction ?? 'neutral'),
        });
      }
    }
  }

  // Extract narrative from first assessment with one
  const narrative = detail?.assessments?.find(a => a.narrative)?.narrative as string | undefined;

  return (
    <Drawer
      isOpen={!!item}
      onClose={onClose}
      title={item.event_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
      subtitle={item.event_date ?? undefined}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', fontFamily: 'var(--font-body)' }}>
        {/* Badges row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '3px 10px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              background: severityColor,
              color: '#fff',
            }}
          >
            {item.severity}
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '3px 10px',
              borderRadius: '999px',
              fontSize: '11px',
              fontWeight: 600,
              border: `1px solid ${trust.color}`,
              color: trust.color,
            }}
          >
            Trust: {trust.text} ({Math.round(item.trust_score * 100)}%)
          </span>
        </div>

        {/* Description */}
        <div>
          <h3 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Description
          </h3>
          <p style={{ fontSize: '14px', lineHeight: 1.6, color: 'var(--color-ink)' }}>
            {item.description}
          </p>
        </div>

        {/* Source link */}
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '13px',
              color: 'var(--color-accent)',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            <ExternalLink size={13} />
            View source
          </a>
        )}

        {/* Affected Entities */}
        {affectedEntities.length > 0 && (
          <div>
            <h3 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Affected Entities
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {affectedEntities.map((e, i) => (
                <div
                  key={`${e.name}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'var(--color-surface-2)',
                  }}
                >
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      color: entityTypeColor(e.type),
                      minWidth: '60px',
                    }}
                  >
                    {e.type}
                  </span>
                  <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)', flex: 1 }}>
                    {e.name}
                  </span>
                  <span style={{ fontSize: '14px' }}>
                    {directionArrow(e.direction)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Impact Narrative */}
        {narrative && (
          <div>
            <h3 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Impact Narrative
            </h3>
            <p style={{ fontSize: '13px', lineHeight: 1.6, color: 'var(--color-ink-2)' }}>
              {narrative}
            </p>
          </div>
        )}

        {/* Dismiss button */}
        <button
          type="button"
          onClick={handleDismiss}
          style={{
            padding: '10px 20px',
            borderRadius: '8px',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface-2)',
            color: 'var(--color-ink-2)',
            fontSize: '13px',
            fontWeight: 500,
            fontFamily: 'var(--font-body)',
            cursor: 'pointer',
            transition: 'background 0.15s',
            alignSelf: 'flex-start',
          }}
        >
          Dismiss event
        </button>
      </div>
    </Drawer>
  );
}

function entityTypeColor(type: string): string {
  const map: Record<string, string> = {
    drug: 'var(--color-drug)',
    company: 'var(--color-company)',
    trial: 'var(--color-trial)',
    therapeutic_area: 'var(--color-ta)',
    mechanism: 'var(--color-mechanism)',
    literature: 'var(--color-literature)',
  };
  return map[type] ?? 'var(--color-ink-3)';
}

function directionArrow(direction: string): string {
  if (direction === 'positive') return '\u2191';
  if (direction === 'negative') return '\u2193';
  return '\u2194';
}
