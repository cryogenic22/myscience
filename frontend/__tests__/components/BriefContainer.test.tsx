/**
 * UX-Brief — BriefContainer tests.
 *
 * Covers loading → not-created (null) → ready (renders the BCB), plus error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  engagementBriefApi: { get: vi.fn() },
}));

// EntityComments has its own api dependency + tests; stub it here.
vi.mock('../../src/components/ci/EntityComments', () => ({
  default: ({ targetType, targetId }: { targetType: string; targetId: string }) => (
    <div data-testid="brief-comments-stub">{targetType}:{targetId}</div>
  ),
}));

import { engagementBriefApi } from '../../src/api';
import BriefContainer from '../../src/components/ci/BriefContainer';

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

function bcb(overrides: Partial<any> = {}) {
  return {
    id: 'bcb1', engagement_id: 'e1', focal_asset: 'drug:semaglutide', situation: 'defense',
    strategic_decisions: [
      { statement: 'Defend formulary tier vs tirzepatide', rationale: 'Protect access before the GLP-1 class consolidates.' },
    ],
    competitive_set: [
      { entity_ref: 'tirzepatide', threat_level: 'high', note: 'Zepbound obesity push' },
    ],
    success_criteria: ['Hold ≥ 40% NBRx share'],
    constraints: ['No price war below floor'],
    created_by: 'lead', created_at: '2026-06-01T00:00:00Z',
    signed_off: false, signed_off_by: null, signed_off_at: null,
    ...overrides,
  };
}

describe('BriefContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the not-created state when no brief exists', async () => {
    (engagementBriefApi.get as any).mockResolvedValue(null);
    render(<BriefContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('brief-empty')).toBeInTheDocument());
  });

  it('renders the brief: decisions, competitive set, criteria, sign-off', async () => {
    (engagementBriefApi.get as any).mockResolvedValue(bcb());
    render(<BriefContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('brief-ready')).toBeInTheDocument());
    expect(screen.getByText(/Defend formulary tier vs tirzepatide/)).toBeInTheDocument();
    expect(screen.getByText('tirzepatide')).toBeInTheDocument();
    expect(screen.getByText(/Hold ≥ 40% NBRx share/)).toBeInTheDocument();
    expect(screen.getByTestId('brief-signoff')).toHaveTextContent(/draft/i);
    // UX08: a discussion thread is mounted on the brief.
    expect(screen.getByTestId('brief-comments-stub')).toHaveTextContent('brief:bcb1');
  });

  it('shows signed-off status when the brief is signed off', async () => {
    (engagementBriefApi.get as any).mockResolvedValue(
      bcb({ signed_off: true, signed_off_by: 'lead', signed_off_at: '2026-06-01T01:00:00Z' }));
    render(<BriefContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('brief-ready')).toBeInTheDocument());
    expect(screen.getByTestId('brief-signoff')).toHaveTextContent(/signed off/i);
  });

  it('shows an error with retry on failure', async () => {
    (engagementBriefApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<BriefContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('brief-error')).toBeInTheDocument());
  });
});
