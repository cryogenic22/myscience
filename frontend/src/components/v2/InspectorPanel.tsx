/**
 * InspectorPanel — right panel showing entity detail from real API data.
 *
 * PURE component: receives all data via props, no internal API calls.
 * NewWorkspace owns fetching and passes inspectorDetail + loading state.
 *
 * Sections: Header, Properties (collapsible), Relationships (collapsible),
 *           Evidence (collapsible), Actions (always visible).
 */

import { useState, useCallback } from 'react';
import Panel from './Panel';
import EntityDot from './EntityDot';
import Badge from './Badge';
import ConfidenceBar from './ConfidenceBar';
import Button from './Button';
import Skeleton from './Skeleton';
import type { GraphNode, CatalogEntityDetail } from '../../api';
import {
  filterProperties,
  groupLinksByType,
  extractEvidenceLinks,
} from '../../utils/inspector-helpers';

/* ── Props ────────────────────────────────────────────────── */

interface InspectorPanelProps {
  entity: GraphNode;
  detail: CatalogEntityDetail | null;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onExplore: (entityType: string, entityId: string) => void;
  onEntityClick: (entityId: string, entityType: string) => void;
}

/* ── Collapsible Section ──────────────────────────────────── */

function Section({
  title,
  defaultOpen = true,
  count,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  count?: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <div style={{ borderTop: '1px solid var(--surface-secondary)' }}>
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
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          {title}
          {count !== undefined && count > 0 && (
            <Badge label={String(count)} variant="default" size="sm" />
          )}
        </span>
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
        <div style={{ padding: '0 var(--space-4) var(--space-4)' }}>{children}</div>
      )}
    </div>
  );
}

/* ── Clickable entity label (used in relationships) ───────── */

function EntityLabel({
  entityId,
  entityType,
  label,
  onClick,
}: {
  entityId: string;
  entityType: string;
  label: string;
  onClick: (entityId: string, entityType: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(entityId, entityType)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        border: 'none',
        background: 'transparent',
        cursor: 'pointer',
        fontFamily: 'var(--font-body)',
        fontSize: 'var(--text-xs)',
        color: 'var(--accent)',
        padding: '2px 0',
        transition: `opacity var(--duration-fast) ease`,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.opacity = '0.7';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.opacity = '1';
      }}
      title={`View ${label}`}
    >
      {label}
    </button>
  );
}

/* ── Main Component ───────────────────────────────────────── */

export default function InspectorPanel({
  entity,
  detail,
  isLoading,
  error,
  onClose,
  onExplore,
  onEntityClick,
}: InspectorPanelProps) {
  // Compute derived data from detail
  const qualityScore =
    detail?.entity?.quality_score != null
      ? Number(detail.entity.quality_score)
      : entity.properties?.quality_score != null
        ? Number(entity.properties.quality_score)
        : undefined;

  const displayProps = detail
    ? filterProperties(detail.entity)
    : entity.properties
      ? filterProperties(entity.properties)
      : [];

  const linkGroups = detail
    ? groupLinksByType(detail.links, entity.entity_id)
    : [];

  const evidenceLinks = detail
    ? extractEvidenceLinks(detail.links, entity.entity_id)
    : [];

  return (
    <Panel side="right" width={320}>
      {/* ── Header ──────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--surface-secondary)',
          flexShrink: 0,
        }}
      >
        {/* Top row: dot + name + close */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
          }}
        >
          <EntityDot type={entity.entity_type} size="md" />
          <span
            style={{
              flex: 1,
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-lg)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={entity.label}
          >
            {entity.label}
          </span>
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
        </div>

        {/* Entity type badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Badge
            label={entity.entity_type.replace(/_/g, ' ')}
            variant="info"
            size="sm"
          />
          {detail && (
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
              }}
            >
              {detail.links.length} connections
            </span>
          )}
        </div>

        {/* Quality / confidence bar */}
        {qualityScore !== undefined && !isNaN(qualityScore) && (
          <div>
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-secondary)',
                marginBottom: 'var(--space-1)',
              }}
            >
              Data Quality
            </div>
            <ConfidenceBar
              value={qualityScore > 1 ? qualityScore / 100 : qualityScore}
              showLabel
            />
          </div>
        )}
      </div>

      {/* ── Scrollable body ──────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Error state */}
        {error && (
          <div
            style={{
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-3)',
              alignItems: 'center',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--confidence-low)',
                lineHeight: 1.5,
              }}
            >
              Failed to load details
            </div>
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
                lineHeight: 1.4,
                maxWidth: 240,
              }}
            >
              {error.length > 200 ? error.slice(0, 197) + '...' : error}
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onExplore(entity.entity_type, entity.entity_id)}
            >
              Retry
            </Button>
          </div>
        )}

        {/* Properties Section */}
        <Section title="Properties" defaultOpen={true}>
          {isLoading ? (
            <Skeleton variant="line" lines={5} />
          ) : displayProps.length > 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              {displayProps.map((prop) => (
                <div
                  key={prop.key}
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
                    {prop.label}
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
                    title={prop.value}
                  >
                    {prop.value}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
              }}
            >
              No properties available
            </div>
          )}
        </Section>

        {/* Relationships Section */}
        <Section
          title="Relationships"
          defaultOpen={true}
          count={detail ? detail.links.length : undefined}
        >
          {isLoading ? (
            <Skeleton variant="line" lines={4} />
          ) : linkGroups.length > 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-3)',
              }}
            >
              {linkGroups.map((group) => (
                <div key={group.entityType}>
                  {/* Group header: dot + type + count */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-2)',
                      marginBottom: 'var(--space-1)',
                    }}
                  >
                    <EntityDot type={group.entityType} size="sm" />
                    <span
                      style={{
                        fontSize: 'var(--text-xs)',
                        color: 'var(--text-secondary)',
                        fontWeight: 500,
                        flex: 1,
                        textTransform: 'capitalize',
                      }}
                    >
                      {group.entityType.replace(/_/g, ' ')}
                    </span>
                    <Badge
                      label={String(group.links.length)}
                      variant="default"
                      size="sm"
                    />
                  </div>

                  {/* Sample labels (up to 3, clickable) */}
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      paddingLeft: 'var(--space-4)',
                    }}
                  >
                    {group.sampleLabels.map((sample) => (
                      <EntityLabel
                        key={sample.entityId}
                        entityId={sample.entityId}
                        entityType={sample.entityType}
                        label={sample.label}
                        onClick={onEntityClick}
                      />
                    ))}
                    {group.links.length > 3 && (
                      <span
                        style={{
                          fontSize: 'var(--text-xs)',
                          color: 'var(--text-tertiary)',
                          padding: '2px 0',
                        }}
                      >
                        +{group.links.length - 3} more
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
              }}
            >
              {detail ? 'No relationships found' : 'Loading...'}
            </div>
          )}
        </Section>

        {/* Evidence Section */}
        <Section title="Evidence" defaultOpen={false} count={evidenceLinks.length || undefined}>
          {isLoading ? (
            <Skeleton variant="line" lines={3} />
          ) : evidenceLinks.length > 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              {evidenceLinks.slice(0, 10).map((ev, i) => (
                <button
                  key={`${ev.entityId}-${i}`}
                  type="button"
                  onClick={() => onEntityClick(ev.entityId, ev.entityType)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    padding: 'var(--space-1) 0',
                    fontFamily: 'var(--font-body)',
                    transition: `opacity var(--duration-fast) ease`,
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.opacity = '0.7';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.opacity = '1';
                  }}
                >
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '100%',
                    }}
                    title={ev.label}
                  >
                    {ev.label}
                  </span>
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-tertiary)',
                      textTransform: 'lowercase',
                    }}
                  >
                    {ev.linkType.replace(/_/g, ' ')}
                  </span>
                </button>
              ))}
              {evidenceLinks.length > 10 && (
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  +{evidenceLinks.length - 10} more
                </span>
              )}
            </div>
          ) : (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
                lineHeight: 1.5,
              }}
            >
              No evidence links found for this entity.
            </div>
          )}
        </Section>

        {/* Actions — always visible at bottom */}
        <div
          style={{
            padding: 'var(--space-4)',
            borderTop: '1px solid var(--surface-secondary)',
            display: 'flex',
            gap: 'var(--space-2)',
          }}
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onExplore(entity.entity_type, entity.entity_id)}
            icon={
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
                <path d="M11 8v6" />
                <path d="M8 11h6" />
              </svg>
            }
          >
            Explore
          </Button>
        </div>
      </div>
    </Panel>
  );
}
