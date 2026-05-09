/**
 * SPEC_030 Stage 3 — decisionBriefsApi contract tests.
 *
 * These assert the typed client added to frontend/src/api.ts produces
 * requests that match schema/openapi.json (SPEC_023 contract). Tests
 * use a fetch-spy to inspect URL, method, headers, and body shape.
 *
 * Shipping criterion: every endpoint listed in SPEC_023 §API surface
 * has at least one positive test (correct request shape) and one
 * envelope test (4xx/5xx surfacing as a typed error).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { makeBrief, makeOption, setRole } from './_fixtures';
import type { BriefState, DecisionBrief, DecisionBriefOption } from '../../../src/api';

// ─── Mock fetch ─────────────────────────────────────────────
const mockFetch = vi.fn();
beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockFetch.mockReset();
  setRole('uploader');
});

function jsonResponse<T>(body: T, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// ─── Tests ──────────────────────────────────────────────────

describe('decisionBriefsApi.list', () => {
  it('issues GET /decision-briefs with cursor + limit query params', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ briefs: [], next_cursor: null, count: 0 }),
    );
    await decisionBriefsApi.list({ limit: 25, cursor: 'abc' });
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('/decision-briefs');
    expect(url).toContain('limit=25');
    expect(url).toContain('cursor=abc');
    expect(mockFetch.mock.calls[0][1]?.method ?? 'GET').toBe('GET');
  });

  it('filters by state, owner_user_id, trigger_kind', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(jsonResponse({ briefs: [], next_cursor: null, count: 0 }));
    await decisionBriefsApi.list({
      state: 'human_review' as BriefState,
      owner_user_id: 'u-1',
      trigger_kind: 'cluster',
    });
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('state=human_review');
    expect(url).toContain('owner_user_id=u-1');
    expect(url).toContain('trigger_kind=cluster');
  });

  it('returns typed list (briefs, next_cursor, count)', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const brief = makeBrief();
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ briefs: [brief], next_cursor: 'next', count: 1 }),
    );
    const result = await decisionBriefsApi.list();
    expect(result.briefs).toHaveLength(1);
    expect(result.briefs[0].brief_id).toBe('b-001');
    expect(result.next_cursor).toBe('next');
    expect(result.count).toBe(1);
  });

  it('surfaces error envelope on 5xx', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ error: { code: 500, type: 'internal_error', message: 'boom' } }, 500),
    );
    await expect(decisionBriefsApi.list()).rejects.toThrow();
  });
});

describe('decisionBriefsApi.get', () => {
  it('issues GET /decision-briefs/{id} returning full brief with options + state_log', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const brief = makeBrief({ options: [makeOption()] });
    mockFetch.mockResolvedValueOnce(jsonResponse(brief));
    const result = await decisionBriefsApi.get('b-001');
    expect(mockFetch.mock.calls[0][0]).toContain('/decision-briefs/b-001');
    expect(result.options).toHaveLength(1);
    expect(result.state_log).toHaveLength(1);
  });

  it('throws on 404 with envelope', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ error: { code: 404, type: 'not_found', message: 'no such brief' } }, 404),
    );
    await expect(decisionBriefsApi.get('nope')).rejects.toThrow();
  });
});

describe('decisionBriefsApi.create', () => {
  it('POSTs minimal body { question } and returns the new brief', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const created = makeBrief({ brief_id: 'b-NEW' });
    mockFetch.mockResolvedValueOnce(jsonResponse(created, 201));
    const result = await decisionBriefsApi.create({ question: 'What now?' } as Partial<DecisionBrief> & { question: string });
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string).question).toBe('What now?');
    expect(result.brief_id).toBe('b-NEW');
  });
});

describe('decisionBriefsApi.patch', () => {
  it('PATCHes only the fields provided', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const updated = makeBrief({ time_horizon_days: 30 });
    mockFetch.mockResolvedValueOnce(jsonResponse(updated));
    await decisionBriefsApi.patch('b-001', { time_horizon_days: 30 });
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ time_horizon_days: 30 });
  });

  it('409 when brief not editable (locked state) surfaces as typed error', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ error: { code: 409, type: 'invalid_state', message: 'locked' } }, 409),
    );
    await expect(decisionBriefsApi.patch('b-001', { question: 'edit' })).rejects.toThrow();
  });
});

describe('decisionBriefsApi.archive', () => {
  it('issues DELETE /decision-briefs/{id}', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));
    await decisionBriefsApi.archive('b-001');
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('DELETE');
  });
});

describe('decisionBriefsApi.addOption', () => {
  it('POSTs option body and returns the new DecisionBriefOption', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const opt = makeOption({ option_id: 'opt-NEW' });
    mockFetch.mockResolvedValueOnce(jsonResponse(opt, 201));
    const result = await decisionBriefsApi.addOption('b-001', {
      label: 'Hold position',
      description: null,
      predicted_outcome: null,
      cost_estimate: null,
      risk_notes: null,
    } as Omit<DecisionBriefOption, 'option_id' | 'brief_id' | 'ordinal' | 'created_at'>);
    expect(result.option_id).toBe('opt-NEW');
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(mockFetch.mock.calls[0][0]).toContain('/decision-briefs/b-001/options');
  });
});

describe('decisionBriefsApi.removeOption', () => {
  it('issues DELETE /decision-briefs/{id}/options/{option_id}', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    // 204 No Content per FastAPI route — Response cannot have a body for 204
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await decisionBriefsApi.removeOption('b-001', 'opt-1');
    expect(mockFetch.mock.calls[0][0]).toContain('/decision-briefs/b-001/options/opt-1');
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('DELETE');
  });
});

describe('decisionBriefsApi.transition', () => {
  it('POSTs { to_state, reason } and returns the updated brief', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    const updated = makeBrief({ state: 'human_review' });
    mockFetch.mockResolvedValueOnce(jsonResponse(updated));
    const result = await decisionBriefsApi.transition('b-001', 'human_review', 'Ready for review');
    expect(result.state).toBe('human_review');
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      to_state: 'human_review',
      reason: 'Ready for review',
    });
  });

  it('omits reason from body when not provided', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(jsonResponse(makeBrief()));
    await decisionBriefsApi.transition('b-001', 'human_review');
    const body = JSON.parse((mockFetch.mock.calls[0][1] as RequestInit).body as string);
    expect(body.reason).toBeUndefined();
  });

  it('409 illegal-transition surfaces typed error', async () => {
    const { decisionBriefsApi } = await import('../../../src/api');
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ error: { code: 409, type: 'invalid_transition', message: 'cannot draft → committed' } }, 409),
    );
    await expect(decisionBriefsApi.transition('b-001', 'committed')).rejects.toThrow();
  });
});
