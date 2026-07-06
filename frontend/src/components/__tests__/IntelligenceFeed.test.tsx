import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { IntelligenceFeedItem } from '../../api';

/* ── Mock API ────────────────────────────────────────── */

const { mockIntelligenceFeed, mockIntelligenceDismiss, mockTraverse } = vi.hoisted(() => ({
  mockIntelligenceFeed: vi.fn(),
  mockIntelligenceDismiss: vi.fn(),
  mockTraverse: vi.fn(),
}));

vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api');
  return {
    ...actual,
    api: {
      ...actual.api,
      intelligenceFeed: mockIntelligenceFeed,
      intelligenceDismiss: mockIntelligenceDismiss,
      traverse: mockTraverse,
    },
  };
});

// Mock KnowledgeGraph to avoid canvas issues in JSDOM
vi.mock('../KnowledgeGraph', () => ({
  default: () => <div data-testid="mock-knowledge-graph">Graph</div>,
}));

import { IntelligenceFeed } from '../intelligence/IntelligenceFeed';
import { EventCard, groupEventsForDigest } from '../intelligence/EventCard';

/* ── Test data ───────────────────────────────────────── */

function makeItem(overrides: Partial<IntelligenceFeedItem> = {}): IntelligenceFeedItem {
  return {
    event_id: `evt-${Math.random().toString(36).slice(2, 8)}`,
    event_type: 'fda_approval',
    event_date: '2026-04-01',
    description: 'FDA approves Keytruda for adjuvant melanoma',
    source_url: null,
    source_tier: 'T1',
    trust_score: 0.92,
    primary_entity_name: 'Keytruda',
    primary_entity_type: 'drug',
    severity: 'medium',
    impact_count: 5,
    max_impact_magnitude: 0.8,
    status: 'active',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

/* ── Tests ────────────────────────────────────────────── */

describe('IntelligenceFeed', () => {
  beforeEach(() => {
    mockIntelligenceFeed.mockReset();
    mockIntelligenceDismiss.mockReset();
    mockTraverse.mockReset();
    mockTraverse.mockResolvedValue({ nodes: [], edges: [] });
  });

  it('renders loading state', () => {
    // Make the feed never resolve to keep loading state
    mockIntelligenceFeed.mockReturnValue(new Promise(() => {}));
    render(<IntelligenceFeed />);
    expect(screen.getByText('Loading feed...')).toBeInTheDocument();
  });

  it('critical severity shows pulsing red dot', async () => {
    const criticalItem = makeItem({ severity: 'critical', event_id: 'crit-1' });
    mockIntelligenceFeed.mockResolvedValue({ items: [criticalItem], total: 1 });

    render(<IntelligenceFeed />);

    await waitFor(() => {
      const dot = screen.getByTestId('severity-dot-critical');
      expect(dot).toBeInTheDocument();
      // Check that pulse animation is applied
      expect(dot.style.animation).toContain('severity-pulse');
    });
  });

  it('high severity shows amber pulsing dot', async () => {
    const highItem = makeItem({ severity: 'high', event_id: 'high-1' });
    mockIntelligenceFeed.mockResolvedValue({ items: [highItem], total: 1 });

    render(<IntelligenceFeed />);

    await waitFor(() => {
      const dot = screen.getByTestId('severity-dot-high');
      expect(dot).toBeInTheDocument();
      expect(dot.style.animation).toContain('severity-pulse');
    });
  });

  it('medium severity shows static dot (no pulse)', async () => {
    const medItem = makeItem({ severity: 'medium', event_id: 'med-1' });
    mockIntelligenceFeed.mockResolvedValue({ items: [medItem], total: 1 });

    render(<IntelligenceFeed />);

    await waitFor(() => {
      const dot = screen.getByTestId('severity-dot-medium');
      expect(dot).toBeInTheDocument();
      // No pulse animation for medium
      expect(dot.style.animation).toBe('');
    });
  });

  it('actionable buttons render on feed cards', async () => {
    const item = makeItem({ severity: 'medium', event_id: 'btn-1' });
    mockIntelligenceFeed.mockResolvedValue({ items: [item], total: 1 });

    const onAskInChat = vi.fn();
    render(<IntelligenceFeed onAskInChat={onAskInChat} />);

    await waitFor(() => {
      expect(screen.getByText('View landscape')).toBeInTheDocument();
      expect(screen.getByText('Compare')).toBeInTheDocument();
      expect(screen.getByText('Ask AI')).toBeInTheDocument();
    });
  });

  it('"Ask AI" button calls onAskInChat with correct question', async () => {
    const item = makeItem({
      severity: 'medium',
      event_id: 'ask-1',
      description: 'Phase III results positive',
    });
    mockIntelligenceFeed.mockResolvedValue({ items: [item], total: 1 });

    const onAskInChat = vi.fn();
    render(<IntelligenceFeed onAskInChat={onAskInChat} />);

    await waitFor(() => {
      expect(screen.getByText('Ask AI')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Ask AI'));
    expect(onAskInChat).toHaveBeenCalledWith(
      'Tell me about the impact of Phase III results positive',
    );
  });

  it('"View landscape" button calls onAskInChat', async () => {
    const item = makeItem({
      severity: 'medium',
      event_id: 'land-1',
      primary_entity_name: 'Keytruda',
    });
    mockIntelligenceFeed.mockResolvedValue({ items: [item], total: 1 });

    const onAskInChat = vi.fn();
    render(<IntelligenceFeed onAskInChat={onAskInChat} />);

    await waitFor(() => {
      expect(screen.getByText('View landscape')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('View landscape'));
    expect(onAskInChat).toHaveBeenCalledWith(
      'Show the competitive landscape for Keytruda',
    );
  });

  it('does not show action buttons when onAskInChat is not provided', async () => {
    const item = makeItem({ severity: 'medium', event_id: 'no-btn-1' });
    mockIntelligenceFeed.mockResolvedValue({ items: [item], total: 1 });

    render(<IntelligenceFeed />);

    await waitFor(() => {
      expect(screen.getByText(item.description)).toBeInTheDocument();
    });

    expect(screen.queryByText('Ask AI')).toBeNull();
    expect(screen.queryByText('View landscape')).toBeNull();
  });

  it('shows empty state when no events', async () => {
    mockIntelligenceFeed.mockResolvedValue({ items: [], total: 0 });

    render(<IntelligenceFeed />);

    await waitFor(() => {
      expect(screen.getByText(/All clear/)).toBeInTheDocument();
    });
  });

  it('shows an error (not the "All clear" empty state) when the feed fails', async () => {
    mockIntelligenceFeed.mockRejectedValue(new Error('feed 500'));

    render(<IntelligenceFeed />);

    const err = await screen.findByTestId('feed-error');
    expect(err).toHaveTextContent(/couldn't load/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    // A down pipeline must never read as a calm, healthy empty inbox.
    expect(screen.queryByText(/All clear/)).not.toBeInTheDocument();
  });

  it('retry re-fetches the feed and recovers', async () => {
    mockIntelligenceFeed
      .mockRejectedValueOnce(new Error('feed 500'))
      .mockResolvedValueOnce({ items: [makeItem({ event_id: 'ok-1', description: 'Recovered event' })], total: 1 });

    render(<IntelligenceFeed />);

    fireEvent.click(await screen.findByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByText('Recovered event')).toBeInTheDocument());
    expect(screen.queryByTestId('feed-error')).not.toBeInTheDocument();
  });
});

describe('EventCard standalone', () => {
  it('renders with severity dot and description', () => {
    const item = makeItem({ severity: 'low', event_id: 'card-1', description: 'Trial completed' });
    const onClick = vi.fn();
    const onDismiss = vi.fn();

    render(<EventCard item={item} onClick={onClick} onDismiss={onDismiss} />);

    expect(screen.getByTestId('severity-dot-low')).toBeInTheDocument();
    expect(screen.getByText('Trial completed')).toBeInTheDocument();
  });
});

describe('groupEventsForDigest', () => {
  it('groups related events by entity_type + event_type within 24h', () => {
    const now = new Date().toISOString();
    const items: IntelligenceFeedItem[] = [
      makeItem({ event_id: 'a', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'b', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'c', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'd', event_type: 'trial_result', primary_entity_type: 'trial', created_at: now }),
    ];

    const groups = groupEventsForDigest(items);

    // Should create one group for drug::fda_approval (3 items)
    // trial_result only has 1 item so it stays ungrouped
    expect(groups.length).toBe(1);
    expect(groups[0].items.length).toBe(3);
    expect(groups[0].eventType).toBe('fda_approval');
    expect(groups[0].entityType).toBe('drug');
  });

  it('does not group events older than 24h', () => {
    const oldDate = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
    const items: IntelligenceFeedItem[] = [
      makeItem({ event_id: 'old-a', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: oldDate }),
      makeItem({ event_id: 'old-b', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: oldDate }),
    ];

    const groups = groupEventsForDigest(items);
    expect(groups.length).toBe(0);
  });

  it('picks highest severity for group', () => {
    const now = new Date().toISOString();
    const items: IntelligenceFeedItem[] = [
      makeItem({ event_id: 'sev-a', severity: 'low', event_type: 'x', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'sev-b', severity: 'critical', event_type: 'x', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'sev-c', severity: 'medium', event_type: 'x', primary_entity_type: 'drug', created_at: now }),
    ];

    const groups = groupEventsForDigest(items);
    expect(groups.length).toBe(1);
    expect(groups[0].highestSeverity).toBe('critical');
  });
});

describe('Digest mode in IntelligenceFeed', () => {
  beforeEach(() => {
    mockIntelligenceFeed.mockReset();
    mockIntelligenceDismiss.mockReset();
    mockTraverse.mockReset();
    mockTraverse.mockResolvedValue({ nodes: [], edges: [] });
  });

  it('shows digest toggle and groups related events', async () => {
    const now = new Date().toISOString();
    const items = [
      makeItem({ event_id: 'dg-1', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'dg-2', event_type: 'fda_approval', primary_entity_type: 'drug', created_at: now }),
      makeItem({ event_id: 'dg-3', event_type: 'trial_result', primary_entity_type: 'trial', created_at: now }),
    ];
    mockIntelligenceFeed.mockResolvedValue({ items, total: 3 });

    render(<IntelligenceFeed />);

    // Wait for items to load
    await waitFor(() => {
      expect(screen.getByText('Digest')).toBeInTheDocument();
    });

    // Switch to digest mode
    fireEvent.click(screen.getByText('Digest'));

    // Should show a digest group for the 2 fda_approval/drug events
    await waitFor(() => {
      expect(screen.getByText(/2 new fda approval events for drug/i)).toBeInTheDocument();
    });
  });
});
