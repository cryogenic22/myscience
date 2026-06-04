/**
 * Loop #21 — Three-row live agent activity feed.
 *
 * Replaces the static AgentIdentityStrip on surfaces that want to show
 * the three agents actually doing work. Each row: glyph + name +
 * relative timestamp + activity text. Driven by polled data.
 */
import AgentGlyph, { AGENTS, type AgentId } from './AgentGlyph';
import NudgeMenu from '../ci/NudgeMenu';
import type { AgentActivity, ActivityKind } from '../../types/agents';

const ORDER: AgentId[] = ['sentinel', 'strategist', 'curator'];

const KIND_TONE: Record<ActivityKind, string> = {
  started: 'var(--color-ink-3)',
  progress: '#1a4c80',
  completed: '#0a5a3f',
  failed: '#B91C1C',
};

function relativeTime(iso: string): string {
  const now = Date.now();
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const secs = Math.max(0, Math.floor((now - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function AgentRow({ id, activity }: { id: AgentId; activity?: AgentActivity }) {
  const meta = AGENTS[id];
  return (
    <div
      data-agent-row
      data-agent-id={id}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        padding: '10px 0',
        borderBottom: '1px solid var(--color-line)',
      }}
    >
      <div style={{ paddingTop: '2px' }}>
        <AgentGlyph agent={id} status={activity ? 'active' : 'idle'} />
      </div>
      <div className="min-w-0" style={{ flex: 1 }}>
        <div className="flex items-baseline justify-between gap-2">
          <span
            className="text-[12px] font-medium"
            style={{ color: 'var(--color-ink)' }}
          >
            {meta.name}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {activity ? (
              <span
                className="text-[10px]"
                style={{ color: 'var(--color-ink-4)', whiteSpace: 'nowrap' }}
              >
                {relativeTime(activity.timestamp)}
              </span>
            ) : null}
            <NudgeMenu agent={id} />
          </span>
        </div>
        <div
          className="text-[10px] uppercase mb-1"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
        >
          {meta.role}
        </div>
        {activity ? (
          <div className="flex items-start gap-2">
            <span
              data-activity-kind={activity.kind}
              aria-hidden="true"
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '999px',
                background: KIND_TONE[activity.kind],
                marginTop: '6px',
                flexShrink: 0,
              }}
            />
            <p
              className="text-[12px]"
              style={{
                color: 'var(--color-ink-3)',
                lineHeight: 1.45,
                margin: 0,
              }}
            >
              {activity.text}
            </p>
          </div>
        ) : (
          <div
            data-agent-waiting
            className="text-[11px]"
            style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
          >
            waiting for activity…
          </div>
        )}
      </div>
    </div>
  );
}

function SkeletonRow({ id }: { id: AgentId }) {
  const meta = AGENTS[id];
  return (
    <div
      data-agent-row
      data-agent-skeleton
      data-agent-id={id}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        padding: '10px 0',
        borderBottom: '1px solid var(--color-line)',
        opacity: 0.55,
      }}
    >
      <AgentGlyph agent={id} status="idle" />
      <div className="min-w-0" style={{ flex: 1 }}>
        <div
          className="text-[12px] font-medium"
          style={{ color: 'var(--color-ink)' }}
        >
          {meta.name}
        </div>
        <div
          className="text-[10px] uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
        >
          {meta.role}
        </div>
        <div
          style={{
            marginTop: '6px',
            height: '10px',
            width: '70%',
            background: 'var(--color-surface-2)',
            borderRadius: '4px',
          }}
        />
      </div>
    </div>
  );
}

interface Props {
  activities: AgentActivity[];
  loading?: boolean;
  className?: string;
}

export default function AgentActivityFeed({
  activities,
  loading = false,
  className = '',
}: Props) {
  // Map agent -> most recent activity. Backend should already order
  // newest-first, but defensive sort here costs nothing.
  const latest = new Map<AgentId, AgentActivity>();
  for (const a of activities) {
    const prior = latest.get(a.agent_id);
    if (!prior || a.timestamp > prior.timestamp) {
      latest.set(a.agent_id, a);
    }
  }

  return (
    <div
      role="group"
      aria-label="Agent activity"
      className={className}
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      {ORDER.map((id) => {
        if (loading && !latest.has(id)) {
          return <SkeletonRow key={id} id={id} />;
        }
        return <AgentRow key={id} id={id} activity={latest.get(id)} />;
      })}
    </div>
  );
}
