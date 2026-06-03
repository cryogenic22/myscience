/**
 * Loop B2 — NewEngagementModal tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NewEngagementModal from '../../src/components/ci/NewEngagementModal';

vi.mock('../../src/api', () => ({
  engagementsApi: { create: vi.fn() },
}));

import { engagementsApi } from '../../src/api';

describe('NewEngagementModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns null when open=false', () => {
    const { container } = render(
      <NewEngagementModal open={false} onClose={() => {}} onCreated={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders form fields when open', () => {
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={() => {}} />);
    expect(screen.getByTestId('ne-name')).toBeInTheDocument();
    expect(screen.getByTestId('ne-asset')).toBeInTheDocument();
    expect(screen.getByTestId('ne-situation')).toBeInTheDocument();
    expect(screen.getByTestId('ne-sponsor')).toBeInTheDocument();
  });

  it('submit disabled until name + asset filled', () => {
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={() => {}} />);
    const btn = screen.getByTestId('ne-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);

    fireEvent.change(screen.getByTestId('ne-name'), { target: { value: 'Test' } });
    expect(btn.disabled).toBe(true);

    fireEvent.change(screen.getByTestId('ne-asset'), { target: { value: 'drug:x' } });
    expect(btn.disabled).toBe(false);
  });

  it('happy path: POSTs and fires onCreated with returned engagement', async () => {
    const created = {
      id: 'eng-new', name: 'Test', asset: 'drug:x', sponsor: null,
      situation: 'launch', workshop_date: null, stage: 'brief',
      status: 'draft', scope: {}, created_by: 'u', created_at: '',
      updated_at: '', tenant_scope: null,
    };
    (engagementsApi.create as any).mockResolvedValue(created);
    const onCreated = vi.fn();
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={onCreated} />);

    fireEvent.change(screen.getByTestId('ne-name'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByTestId('ne-asset'), { target: { value: 'drug:x' } });
    fireEvent.click(screen.getByTestId('ne-submit'));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(onCreated).toHaveBeenCalledWith(created);
    expect((engagementsApi.create as any)).toHaveBeenCalledWith({
      name: 'Test', asset: 'drug:x', situation: 'launch', sponsor: undefined,
    });
  });

  it('PB-IX01: pre-fills asset/name/context when seeded from a signal promote', () => {
    render(
      <NewEngagementModal
        open={true}
        onClose={() => {}}
        onCreated={() => {}}
        initialAsset="drug:semaglutide"
        initialName="Semaglutide — signal response"
        initialContext="FDA expands the obesity label."
      />,
    );
    expect((screen.getByTestId('ne-asset') as HTMLInputElement).value).toBe('drug:semaglutide');
    expect((screen.getByTestId('ne-name') as HTMLInputElement).value).toBe('Semaglutide — signal response');
    expect((screen.getByTestId('ne-context') as HTMLTextAreaElement).value).toBe('FDA expands the obesity label.');
    // Seeded form is immediately submittable (name + asset present).
    expect((screen.getByTestId('ne-submit') as HTMLButtonElement).disabled).toBe(false);
  });

  it('renders the agent-context fields (context + key questions)', () => {
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={() => {}} />);
    expect(screen.getByTestId('ne-context')).toBeInTheDocument();
    expect(screen.getByTestId('ne-questions')).toBeInTheDocument();
  });

  it('packs strategic context + key questions into scope for the agents', async () => {
    const created = {
      id: 'eng-ctx', name: 'Test', asset: 'drug:x', sponsor: null,
      situation: 'defense', workshop_date: null, stage: 'brief',
      status: 'draft', scope: {}, created_by: 'u', created_at: '',
      updated_at: '', tenant_scope: null,
    };
    (engagementsApi.create as any).mockResolvedValue(created);
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={() => {}} />);

    fireEvent.change(screen.getByTestId('ne-name'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByTestId('ne-asset'), { target: { value: 'drug:x' } });
    fireEvent.click(screen.getByTestId('ne-situation-defense'));
    fireEvent.change(screen.getByTestId('ne-context'), {
      target: { value: 'Competitor likely to file for MASH first.' },
    });
    fireEvent.change(screen.getByTestId('ne-questions'), {
      target: { value: 'Who files first?\n  \nWhat is our pricing floor?' },
    });
    fireEvent.click(screen.getByTestId('ne-submit'));

    await waitFor(() => expect(engagementsApi.create as any).toHaveBeenCalledTimes(1));
    expect((engagementsApi.create as any)).toHaveBeenCalledWith({
      name: 'Test', asset: 'drug:x', situation: 'defense', sponsor: undefined,
      scope: {
        context: 'Competitor likely to file for MASH first.',
        // blank middle line is dropped; each question trimmed
        key_questions: ['Who files first?', 'What is our pricing floor?'],
      },
    });
  });

  it('omits scope entirely when no agent context is given', async () => {
    const created = {
      id: 'eng-bare', name: 'Test', asset: 'drug:x', sponsor: null,
      situation: 'launch', workshop_date: null, stage: 'brief',
      status: 'draft', scope: {}, created_by: 'u', created_at: '',
      updated_at: '', tenant_scope: null,
    };
    (engagementsApi.create as any).mockResolvedValue(created);
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={() => {}} />);

    fireEvent.change(screen.getByTestId('ne-name'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByTestId('ne-asset'), { target: { value: 'drug:x' } });
    fireEvent.click(screen.getByTestId('ne-submit'));

    await waitFor(() => expect(engagementsApi.create as any).toHaveBeenCalledTimes(1));
    const arg = (engagementsApi.create as any).mock.calls[0][0];
    expect(arg).not.toHaveProperty('scope');
  });

  it('error path: API failure shows error message, does NOT fire onCreated', async () => {
    (engagementsApi.create as any).mockRejectedValue(new Error('400 bad situation'));
    const onCreated = vi.fn();
    render(<NewEngagementModal open={true} onClose={() => {}} onCreated={onCreated} />);

    fireEvent.change(screen.getByTestId('ne-name'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByTestId('ne-asset'), { target: { value: 'drug:x' } });
    fireEvent.click(screen.getByTestId('ne-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('ne-error')).toBeInTheDocument();
    });
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('clicking outside the dialog calls onClose', () => {
    const onClose = vi.fn();
    render(<NewEngagementModal open={true} onClose={onClose} onCreated={() => {}} />);
    fireEvent.click(screen.getByTestId('new-engagement-modal'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
