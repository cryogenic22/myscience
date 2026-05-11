import AgentGlyph, { AGENTS, type AgentId, type AgentStatus } from './AgentGlyph';

/**
 * PB-201 — Three-agent identity strip.
 *
 * Surfaces Sentinel · Strategist · Curator in a single row with name
 * + role for each. Replaces the opaque "3 agents active" label from
 * `AgentStatusBar` once PB-202 wires SSE-driven status per glyph.
 *
 * Today it's a static identity surface — call sites just mount
 * `<AgentIdentityStrip />` to make the three agents felt across the
 * app. When BE-3 (PR #50) lands, the optional `statuses` prop lets
 * consumers reflect each agent's live state.
 */

const ORDER: AgentId[] = ['sentinel', 'strategist', 'curator'];

interface Props {
  /** Map of agent → status. Undefined entries render without a status dot. */
  statuses?: Partial<Record<AgentId, AgentStatus>>;
  className?: string;
}

export default function AgentIdentityStrip({ statuses, className = '' }: Props) {
  return (
    <div
      role="group"
      aria-label="Active agents"
      className={`flex flex-wrap items-center gap-4 ${className}`.trim()}
    >
      {ORDER.map((id) => {
        const meta = AGENTS[id];
        const status = statuses?.[id];
        return (
          <div key={id} className="flex items-center gap-2.5 min-w-0">
            <AgentGlyph agent={id} status={status} />
            <div className="leading-tight min-w-0">
              <div className="mz-text-sm font-medium" style={{ color: 'var(--color-ink-2)' }}>
                {meta.name}
              </div>
              <div
                className="mz-text-xs uppercase truncate"
                style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em', marginTop: '1px' }}
              >
                {meta.role}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
