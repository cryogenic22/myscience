/**
 * IX-2 — IntelligenceTab tests.
 *
 * The consolidated feed surface: a view toggle over the three (stubbed) child
 * tabs. Verifies initial view, toggling, and that the InboxTab "see signals"
 * callback switches the view internally.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../src/components/ci/DigestTab', () => ({
  default: () => <div data-testid="digest-stub" />,
}));
vi.mock('../../src/components/ci/InboxTab', () => ({
  default: ({ onOpenSignals }: { onOpenSignals?: () => void }) => (
    <div data-testid="inbox-stub"><button data-testid="inbox-see-signals" onClick={onOpenSignals}>signals</button></div>
  ),
}));
vi.mock('../../src/components/ci/SignalsTab', () => ({
  default: () => <div data-testid="signals-stub" />,
}));

import IntelligenceTab from '../../src/components/ci/IntelligenceTab';

const noop = () => {};

describe('IntelligenceTab', () => {
  beforeEach(() => vi.clearAllMocks());

  it('defaults to the Digest view', () => {
    render(<IntelligenceTab onOpenDecision={noop} onOpenWarRoom={noop} />);
    expect(screen.getByTestId('digest-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('inbox-stub')).not.toBeInTheDocument();
  });

  it('honours initialView (deep-link back-compat)', () => {
    render(<IntelligenceTab initialView="signals" onOpenDecision={noop} onOpenWarRoom={noop} />);
    expect(screen.getByTestId('signals-stub')).toBeInTheDocument();
  });

  it('toggles between the three views', () => {
    render(<IntelligenceTab onOpenDecision={noop} onOpenWarRoom={noop} />);
    fireEvent.click(screen.getByTestId('intel-view-stream'));
    expect(screen.getByTestId('inbox-stub')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('intel-view-signals'));
    expect(screen.getByTestId('signals-stub')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('intel-view-digest'));
    expect(screen.getByTestId('digest-stub')).toBeInTheDocument();
  });

  it('the stream view’s "see signals" jumps to the Signals DB view', () => {
    render(<IntelligenceTab initialView="stream" onOpenDecision={noop} onOpenWarRoom={noop} />);
    fireEvent.click(screen.getByTestId('inbox-see-signals'));
    expect(screen.getByTestId('signals-stub')).toBeInTheDocument();
  });
});
