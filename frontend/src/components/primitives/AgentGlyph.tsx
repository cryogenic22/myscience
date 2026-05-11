/**
 * PB-201 — Agent glyph primitive.
 *
 * Renders the three named agents with consistent letters + tinted
 * badge so they read as identities across every surface:
 *   - Sentinel  · SE · teal   · role: Sense
 *   - Strategist · ST · violet · role: Frame · Simulate
 *   - Curator   · CU · green  · role: Learn · Recalibrate
 *
 * Phase 8 verification mandates the noun form (the agents are
 * "Sentinel / Strategist / Curator", not "Sensing / Framing /
 * Curating"). aria-labels and visible labels both use nouns.
 */

export type AgentId = 'sentinel' | 'strategist' | 'curator';
export type AgentStatus = 'idle' | 'active' | 'failed' | 'paused';

export interface AgentMeta {
  id: AgentId;
  name: string;
  glyph: string;
  role: string;
  /** rgb so we can mix with opacity for the badge fill. */
  rgb: string;
}

export const AGENTS: Record<AgentId, AgentMeta> = {
  sentinel: {
    id: 'sentinel',
    name: 'Sentinel',
    glyph: 'SE',
    role: 'Sense',
    rgb: '20, 184, 166', // teal-500
  },
  strategist: {
    id: 'strategist',
    name: 'Strategist',
    glyph: 'ST',
    role: 'Frame · Simulate',
    rgb: '139, 92, 246', // violet-500
  },
  curator: {
    id: 'curator',
    name: 'Curator',
    glyph: 'CU',
    role: 'Learn · Recalibrate',
    rgb: '34, 197, 94', // green-500
  },
};

const STATUS_TONE: Record<AgentStatus, string> = {
  idle: 'rgba(120, 120, 120, 0.6)',
  active: 'rgba(34, 197, 94, 0.9)',
  failed: 'rgba(239, 68, 68, 0.9)',
  paused: 'rgba(245, 158, 11, 0.9)',
};

interface Props {
  agent: AgentId;
  showLabel?: boolean;
  status?: AgentStatus;
}

export default function AgentGlyph({ agent, showLabel = false, status }: Props) {
  const meta = AGENTS[agent];
  const badgeStyle = {
    background: `rgba(${meta.rgb}, 0.18)`,
    color: `rgb(${meta.rgb})`,
    border: `1px solid rgba(${meta.rgb}, 0.45)`,
    width: '28px',
    height: '28px',
    borderRadius: '6px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'DM Mono, ui-monospace, monospace',
    fontSize: '11px',
    fontWeight: 600,
    letterSpacing: '0.5px',
    position: 'relative' as const,
  };
  return (
    <span className="inline-flex items-center gap-2">
      <span
        data-agent={meta.id}
        aria-label={meta.name}
        style={badgeStyle}
      >
        {meta.glyph}
        {status && (
          <span
            data-status={status}
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: '-2px',
              right: '-2px',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: STATUS_TONE[status],
              border: '2px solid var(--color-surface)',
            }}
          />
        )}
      </span>
      {showLabel && (
        <span className="text-[12px]" style={{ color: 'var(--color-ink-2)' }}>
          {meta.name}
        </span>
      )}
    </span>
  );
}
