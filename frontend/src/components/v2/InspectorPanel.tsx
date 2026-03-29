/**
 * InspectorPanel — right panel that appears when an entity is selected.
 * Shows EntityCard (expanded), Properties, Relationships, Evidence sections.
 */

import { useState, useCallback } from 'react';
import Panel from './Panel';
import EntityCard from './EntityCard';
import EntityDot from './EntityDot';
import Badge from './Badge';
import Button from './Button';

interface InspectorEntity {
  id: string;
  type: string;
  name: string;
  properties?: Record<string, unknown>;
}

interface InspectorPanelProps {
  entity?: InspectorEntity;
  onClose?: () => void;
}

/** Collapsible section within the inspector */
function Section({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <div
      style={{
        borderTop: '1px solid var(--border-subtle)',
      }}
    >
      <button
        type="button"
        onClick={toggle}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-4)',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-xs)',
          fontWeight: 600,
          letterSpacing: '0.04em',
          textTransform: 'uppercase' as const,
          color: 'var(--text-tertiary)',
          transition: `color var(--duration-fast) ease`,
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-tertiary)';
        }}
      >
        {title}
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: `transform var(--duration-fast) ease`,
          }}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div style={{ padding: '0 var(--space-4) var(--space-4)' }}>
          {children}
        </div>
      )}
    </div>
  );
}

/** Format a property value for display */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '--';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') {
    if (value.length > 80) return value.slice(0, 77) + '...';
    return value;
  }
  if (Array.isArray(value)) return value.length + ' items';
  return String(value);
}

/** Check if a value looks like a UUID (hide from display) */
function isUUID(value: unknown): boolean {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
  );
}

/** Human-readable property labels */
const PROP_LABELS: Record<string, string> = {
  generic_name: 'Generic Name',
  brand_name: 'Brand Name',
  mechanism_id: 'Mechanism',
  therapeutic_area_id: 'Therapeutic Area',
  approval_date: 'Approval Date',
  phase: 'Phase',
  status: 'Status',
  nct_id: 'NCT ID',
  pmid: 'PMID',
  journal: 'Journal',
  publication_date: 'Published',
  ticker: 'Ticker',
  country: 'Country',
  quality_score: 'Quality',
};

/** Simulated relationship counts for empty state */
const ENTITY_TYPE_CONNECTIONS: Record<string, string[]> = {
  drug: ['trial', 'company', 'mechanism', 'literature'],
  company: ['drug', 'trial', 'patent'],
  trial: ['drug', 'company', 'investigator'],
  mechanism: ['drug', 'therapeutic_area'],
  therapeutic_area: ['drug', 'mechanism', 'trial'],
  literature: ['drug', 'trial'],
};

export default function InspectorPanel({ entity, onClose }: InspectorPanelProps) {
  if (!entity) return null;

  const properties = entity.properties ?? {};
  const displayProps = Object.entries(properties).filter(
    ([key, val]) =>
      !key.startsWith('_') &&
      !key.endsWith('_id') &&
      key !== 'id' &&
      key !== 'entity_id' &&
      key !== 'entity_type' &&
      key !== 'embedding' &&
      key !== 'content_hash' &&
      !isUUID(val),
  );

  const relatedTypes = ENTITY_TYPE_CONNECTIONS[entity.type] ?? ['drug', 'company'];

  return (
    <Panel side="right" width={320}>
      {/* Header with close button */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 500,
            color: 'var(--text-primary)',
          }}
        >
          Inspector
        </span>
        {onClose && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            title="Close inspector"
            aria-label="Close inspector"
            icon={
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            }
          />
        )}
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Entity Card (expanded) */}
        <div style={{ padding: 'var(--space-4)' }}>
          <EntityCard name={entity.name} type={entity.type} />
        </div>

        {/* Properties Section */}
        <Section title="Properties" defaultOpen={true}>
          {displayProps.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {displayProps.map(([key, val]) => (
                <div
                  key={key}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 'var(--space-3)',
                  }}
                >
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-tertiary)',
                      flexShrink: 0,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {PROP_LABELS[key] ?? key.replace(/_/g, ' ')}
                  </span>
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-primary)',
                      textAlign: 'right',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      minWidth: 0,
                    }}
                    title={String(val ?? '')}
                  >
                    {formatValue(val)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-quaternary)' }}>
              No properties available
            </div>
          )}
        </Section>

        {/* Relationships Section */}
        <Section title="Relationships" defaultOpen={true}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {relatedTypes.map((relType) => (
              <div
                key={relType}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  padding: 'var(--space-1) 0',
                }}
              >
                <EntityDot type={relType} size={6} />
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-secondary)',
                    flex: 1,
                    textTransform: 'capitalize',
                  }}
                >
                  {relType.replace(/_/g, ' ')}
                </span>
                <Badge variant="neutral">--</Badge>
              </div>
            ))}
          </div>
        </Section>

        {/* Evidence Section */}
        <Section title="Evidence" defaultOpen={false}>
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-quaternary)',
              lineHeight: 1.5,
            }}
          >
            Evidence snippets will appear here when connected to the graph API.
            Select an entity from the knowledge graph to see supporting data.
          </div>
        </Section>
      </div>
    </Panel>
  );
}
