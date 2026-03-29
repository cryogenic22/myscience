import React, { useState } from 'react';
import EntityDot from './EntityDot';
import ConfidenceBar from './ConfidenceBar';
import Badge from './Badge';

interface EntityCardProps {
  name: string;
  type: string;
  descriptor?: string;
  metadata?: string;
  confidence?: number;
  connections?: Record<string, number>;
  variant?: 'compact' | 'standard' | 'expanded';
  onClick?: () => void;
}

export default function EntityCard({
  name,
  type,
  descriptor,
  metadata,
  confidence,
  connections,
  variant = 'standard',
  onClick,
}: EntityCardProps) {
  const [hovered, setHovered] = useState(false);

  if (variant === 'compact') {
    return (
      <div
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-3)',
          borderRadius: 'var(--radius-md)',
          backgroundColor: 'var(--surface-elevated)',
          cursor: onClick ? 'pointer' : 'default',
          boxShadow: hovered ? 'var(--shadow-sm)' : 'none',
          transform: hovered ? 'translateY(-1px)' : 'none',
          transition: `all var(--duration-fast) var(--ease-out)`,
        }}
      >
        <EntityDot type={type} size="sm" />
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {name}
        </span>
        {descriptor && (
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-secondary)',
            }}
          >
            {descriptor}
          </span>
        )}
      </div>
    );
  }

  /* standard + expanded share the same outer card */
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: 'var(--space-4)',
        borderRadius: 'var(--radius-lg)',
        backgroundColor: 'var(--surface-elevated)',
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: hovered ? 'var(--shadow-sm)' : 'none',
        transform: hovered ? 'translateY(-1px)' : 'none',
        transition: `all var(--duration-fast) var(--ease-out)`,
        border: '1px solid var(--surface-secondary)',
      }}
    >
      {/* Header row: dot + name + type badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
        <EntityDot type={type} size="md" />
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-lg)',
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {name}
        </span>
        <Badge label={type} variant="info" size="sm" />
      </div>

      {/* Descriptor */}
      {descriptor && (
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
            marginBottom: 'var(--space-2)',
          }}
        >
          {descriptor}
        </div>
      )}

      {/* Metadata line */}
      {metadata && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            marginBottom: 'var(--space-3)',
          }}
        >
          {metadata}
        </div>
      )}

      {/* Confidence bar */}
      {confidence !== undefined && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-xs)',
              color: 'var(--text-secondary)',
              marginBottom: 'var(--space-1)',
            }}
          >
            Confidence
          </div>
          <ConfidenceBar value={confidence} showLabel />
        </div>
      )}

      {/* Connection counts */}
      {connections && Object.keys(connections).length > 0 && (
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {Object.entries(connections).map(([key, count]) => (
            <Badge key={key} label={`${count} ${key}`} variant="default" size="sm" />
          ))}
        </div>
      )}

      {/* Expanded: relationship sections placeholder */}
      {variant === 'expanded' && (
        <div
          style={{
            marginTop: 'var(--space-4)',
            paddingTop: 'var(--space-4)',
            borderTop: '1px solid var(--surface-secondary)',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              marginBottom: 'var(--space-2)',
            }}
          >
            Relationships
          </div>
          {connections && Object.entries(connections).map(([key, count]) => (
            <div
              key={key}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: 'var(--space-1) 0',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-sm)',
              }}
            >
              <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{key}</span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-tertiary)',
                }}
              >
                {count}
              </span>
            </div>
          ))}
          {(!connections || Object.keys(connections).length === 0) && (
            <div
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-sm)',
                color: 'var(--text-tertiary)',
                fontStyle: 'italic',
              }}
            >
              No connections yet
            </div>
          )}
        </div>
      )}
    </div>
  );
}
