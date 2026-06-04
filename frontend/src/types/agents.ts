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

/** PB-203 — a bounded action a reviewer can ask of an agent. */
export interface NudgeIntent {
  key: string;
  label: string;
  description: string;
  requires_target: boolean;
  target_kind: string | null;
}

export interface AgentIntentsResponse {
  agent: AgentId;
  intents: NudgeIntent[];
}

/** A queued nudge as returned by POST /agents/{agent}/nudge. */
export interface NudgeRecord {
  id: string;
  agent: AgentId;
  intent: string;
  target: Record<string, unknown> | null;
  note: string | null;
  status: string;
  created_by: string | null;
  created_at: string | null;
}
