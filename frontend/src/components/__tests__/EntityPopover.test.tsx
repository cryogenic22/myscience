import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import NarrativeMessage from '../chat/NarrativeMessage';
import type { Message } from '../ChatMessage';

// Framer-motion minimal mock — renders children without animation
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, ...domProps } = props;
      void initial; void animate; void transition;
      return <div {...domProps}>{children}</div>;
    },
  },
}));

// Mock the api module
const mockEntitySummary = vi.fn();
vi.mock('../../api', () => ({
  api: {
    entitySummary: (...args: unknown[]) => mockEntitySummary(...args),
  },
}));

function makeMessageWithEntities(
  content: string,
  entities: Array<{ name: string; entity_type: string; entity_id?: string }>,
): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content,
    timestamp: new Date(),
    data: {
      entity_focus: entities.map(e => ({
        label: e.name,
        entity_type: e.entity_type,
        entity_id: e.entity_id,
      })),
      evidence: [],
      graph_context: { nodes: [], edges: [], node_count: 0, edge_count: 0 },
      metrics_context: {},
      provenance_summary: {},
      question: '',
    } as Message['data'],
  };
}

const mockSummaryData = {
  entity: { generic_name: 'Aspirin', entity_type: 'drug' },
  connections_by_type: {
    EVIDENCE_FOR: 15,
    INVESTIGATES: 8,
    IN_THERAPEUTIC_AREA: 3,
    TARGETS_MECHANISM: 2,
  },
  connections_by_entity_type: { literature: 15, trial: 8, therapeutic_area: 3, mechanism: 2 },
  total_connections: 28,
};

describe('Entity mention popovers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockEntitySummary.mockReset();
    mockEntitySummary.mockResolvedValue(mockSummaryData);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows popover after hovering entity mention for 300ms', async () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-001');
    expect(mention).toBeInTheDocument();

    // Popover should not exist before hover
    expect(screen.queryByTestId('entity-popover')).toBeNull();

    // Start hovering
    fireEvent.mouseEnter(mention);

    // Should not appear immediately
    expect(screen.queryByTestId('entity-popover')).toBeNull();

    // Advance past the 300ms hover delay
    act(() => { vi.advanceTimersByTime(300); });

    // Now the popover should appear (with loading state)
    expect(screen.getByTestId('entity-popover')).toBeInTheDocument();

    // Wait for the api call to resolve
    await act(async () => {
      await vi.runAllTimersAsync();
    });
  });

  it('popover shows entity type and name', async () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-001');
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });

    // Wait for async data
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const popover = screen.getByTestId('entity-popover');
    expect(popover).toBeInTheDocument();

    // Check entity name is displayed
    const nameEl = screen.getByTestId('entity-popover-name');
    expect(nameEl.textContent).toBe('Aspirin');

    // Check entity type dot is present
    const dot = screen.getByTestId('entity-popover-dot');
    expect(dot).toBeInTheDocument();

    // Check type label is shown — "Drug" from ENTITY_TYPE_LABELS
    expect(popover.textContent).toContain('Drug');
  });

  it('popover shows top connections and total count', async () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-001');
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const popover = screen.getByTestId('entity-popover');

    // Should show top 3 connections: EVIDENCE_FOR(15), INVESTIGATES(8), IN_THERAPEUTIC_AREA(3)
    expect(popover.textContent).toContain('Supporting literature');
    expect(popover.textContent).toContain('15');
    expect(popover.textContent).toContain('Clinical trials');
    expect(popover.textContent).toContain('8');
    expect(popover.textContent).toContain('Therapeutic area');
    expect(popover.textContent).toContain('3');

    // Total connections
    expect(popover.textContent).toContain('28 total connections');
  });

  it('popover is dismissed on mouse leave', async () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-001');

    // Hover to show popover
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(screen.getByTestId('entity-popover')).toBeInTheDocument();

    // Leave the mention
    fireEvent.mouseLeave(mention);

    // Should still be visible (200ms dismiss delay)
    expect(screen.getByTestId('entity-popover')).toBeInTheDocument();

    // Advance past dismiss delay
    act(() => { vi.advanceTimersByTime(200); });

    // Now should be gone
    expect(screen.queryByTestId('entity-popover')).toBeNull();
  });

  it('no popover when entity has no ID metadata', () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug' }], // no entity_id
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    // The entity text should still be rendered and styled
    const text = screen.getByText('Aspirin');
    expect(text).toBeInTheDocument();

    // But there should be no data-testid since there's no entity_id
    expect(screen.queryByTestId(/entity-mention-/)).toBeNull();

    // Hover should not produce a popover
    fireEvent.mouseEnter(text);
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.queryByTestId('entity-popover')).toBeNull();
  });

  it('popover stays visible when mouse moves from mention to popover', async () => {
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-001');

    // Hover to show popover
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const popover = screen.getByTestId('entity-popover');
    expect(popover).toBeInTheDocument();

    // Leave mention (starts 200ms dismiss timer)
    fireEvent.mouseLeave(mention);

    // Quickly enter the popover (cancels dismiss timer)
    fireEvent.mouseEnter(popover);

    // Advance past what would have been the dismiss delay
    act(() => { vi.advanceTimersByTime(300); });

    // Popover should still be visible
    expect(screen.getByTestId('entity-popover')).toBeInTheDocument();
  });

  it('View Profile button calls onEntityClick', async () => {
    const onEntityClick = vi.fn();
    const msg = makeMessageWithEntities(
      'Aspirin is a widely used drug.',
      [{ name: 'Aspirin', entity_type: 'drug', entity_id: 'drug-001' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} onEntityClick={onEntityClick} />);

    const mention = screen.getByTestId('entity-mention-drug-001');
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const viewBtn = screen.getByTestId('entity-popover-view-profile');
    fireEvent.click(viewBtn);

    expect(onEntityClick).toHaveBeenCalledWith('drug-001', 'drug');
  });

  it('caches API responses for repeated hovers', async () => {
    const msg = makeMessageWithEntities(
      'Ibuprofen is a widely used drug.',
      [{ name: 'Ibuprofen', entity_type: 'drug', entity_id: 'drug-cache-test' }],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const mention = screen.getByTestId('entity-mention-drug-cache-test');

    // First hover
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });
    await act(async () => { await vi.runAllTimersAsync(); });

    // Dismiss
    fireEvent.mouseLeave(mention);
    act(() => { vi.advanceTimersByTime(200); });

    expect(mockEntitySummary).toHaveBeenCalledTimes(1);

    // Second hover — should use cache
    fireEvent.mouseEnter(mention);
    act(() => { vi.advanceTimersByTime(300); });
    await act(async () => { await vi.runAllTimersAsync(); });

    // API should not have been called again (cache hit)
    expect(mockEntitySummary).toHaveBeenCalledTimes(1);

    // But popover should still show
    expect(screen.getByTestId('entity-popover')).toBeInTheDocument();
  });
});
