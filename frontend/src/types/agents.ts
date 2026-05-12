/**
 * Loop #21 — Agent activity types.
 *
 * Mirrors what `GET /agents/activity` returns. The three named agents
 * (Sentinel, Strategist, Curator) each surface their latest activity
 * to /ci so the agents feel like colleagues, not static labels.
 */
import type { AgentId } from '../components/primitives/AgentGlyph';

export type ActivityKind = 'started' | 'progress' | 'completed' | 'failed';

export interface AgentActivity {
  agent_id: AgentId;
  kind: ActivityKind;
  text: string;
  timestamp: string;
}

export interface AgentActivityResponse {
  activities: AgentActivity[];
  /** Seconds the client should wait before re-polling. */
  poll_after_seconds?: number;
}
