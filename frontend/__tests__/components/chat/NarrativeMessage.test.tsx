/**
 * NarrativeMessage — structured coverage-limits rendering.
 *
 * The chat response carries honest coverage limits (H1) with source-specific
 * review flags (MZ-XR-20260613-002). They must be surfaced as first-class warning
 * rows so a user can read the honesty without scraping the prose (MZ-XR-002 /
 * MZ-XR-004 exit criterion: "Frontend can read structured limitations and
 * review_flags").
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import NarrativeMessage from '../../../src/components/chat/NarrativeMessage';
import type { Message } from '../../../src/components/ChatMessage';
import type { QueryResponse } from '../../../src/api';

function makeData(over: Partial<QueryResponse> = {}): QueryResponse {
  return {
    question: 'q',
    evidence: [],
    graph_context: { nodes: [], edges: [], node_count: 0, edge_count: 0 },
    metrics_context: {},
    entity_focus: [],
    provenance_summary: {},
    ...over,
  };
}

function makeMsg(data?: QueryResponse, role: 'user' | 'assistant' = 'assistant'): Message {
  return { id: 'm1', role, content: 'Answer text.', timestamp: new Date(), data };
}

describe('NarrativeMessage — coverage limits', () => {
  it('renders structured limitations + review flags as first-class rows', () => {
    const data = makeData({
      limitations: ['No payer policy source is ingested.', 'CMS NADAC currently has no rows.'],
      review_flags: ['NO_PAYER_SOURCE', 'NADAC_NO_ROWS'],
    });
    render(<NarrativeMessage message={makeMsg(data)} isUser={false} />);
    const box = screen.getByTestId('coverage-limits');
    expect(box).toBeInTheDocument();
    expect(box.querySelectorAll('[data-coverage-limit]').length).toBe(2);
    expect(box.querySelector('[data-review-flag="NO_PAYER_SOURCE"]')).not.toBeNull();
    expect(box.querySelector('[data-review-flag="NADAC_NO_ROWS"]')).not.toBeNull();
    // The actual limitation prose is surfaced, not just the flag code.
    expect(screen.getByText(/payer policy source is not ingested|payer policy source is ingested/i)).toBeTruthy();
  });

  it('renders limitations even when there are no review flags', () => {
    const data = makeData({ limitations: ['EMA product information is not ingested.'] });
    render(<NarrativeMessage message={makeMsg(data)} isUser={false} />);
    expect(screen.getByTestId('coverage-limits')).toBeInTheDocument();
    expect(screen.queryByText('NO_PAYER_SOURCE')).toBeNull();
  });

  it('shows no coverage-limits block when there are none', () => {
    render(<NarrativeMessage message={makeMsg(makeData())} isUser={false} />);
    expect(screen.queryByTestId('coverage-limits')).toBeNull();
  });

  it('does not render limits on a user message', () => {
    const data = makeData({ limitations: ['x'], review_flags: ['NO_PAYER_SOURCE'] });
    render(<NarrativeMessage message={makeMsg(data, 'user')} isUser={true} />);
    expect(screen.queryByTestId('coverage-limits')).toBeNull();
  });
});
