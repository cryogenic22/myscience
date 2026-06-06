/**
 * DF — ForgeRoundView tests.
 *
 * Covers the play loop: a round renders its grounded prompt + constrained
 * options; ranking + submit fires the API; the result card shows the score and
 * distinguishes PROMOTED (consensus) / FLAGGED (proposal) / INVALID states; and
 * the session scoreboard renders. The api module is mocked.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  forgeApi: {
    createRound: vi.fn(),
    submitAnswer: vi.fn(),
    session: vi.fn(),
  },
}));

import { forgeApi } from '../../src/api';
import ForgeRoundView from '../../src/components/forge/ForgeRoundView';

function makeRound(overrides: Partial<any> = {}) {
  return {
    id: 'r-1',
    session_id: 's-1',
    round_type: 'what_matters',
    playbook_id: 'compare.drug_x_drug',
    intent: 'compare',
    prompt: 'To compare semaglutide vs tirzepatide, which dimensions matter most?',
    payload: {
      entities: [
        { entity_id: 'd1', entity_type: 'drug', label: 'semaglutide' },
        { entity_id: 'd2', entity_type: 'drug', label: 'tirzepatide' },
      ],
      options: [
        { key: 'efficacy', label: 'Efficacy / endpoints', routes: ['predicate:trial_result'] },
        { key: 'safety', label: 'Safety profile', routes: ['predicate:adverse_event'] },
      ],
      instructions: 'Rank the dimensions.',
    },
    status: 'open',
    created_by: null,
    created_at: null,
    ...overrides,
  };
}

function makeResult(overrides: Partial<any> = {}) {
  return {
    round_id: 'r-1',
    dimension: { key: 'efficacy', label: 'Efficacy / endpoints', sub_question: '', routes: [], required: false, weight: 0.7 },
    validation: { valid: true, errors: [] },
    consensus: { state: 'promoted', agree_count: 2, threshold: 2 },
    playbook_version: 3,
    eval_item: { id: 'ev-1' },
    score: { points: 10, reason: 'valid + consensus promoted to playbook' },
    ...overrides,
  };
}

const SESSION = { session_id: 's-1', rounds: 1, rounds_answered: 0, eval_items: 0, promoted: 0, score: 0 };

describe('ForgeRoundView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (forgeApi.session as any).mockResolvedValue(SESSION);
  });

  it('renders the grounded prompt and the constrained options', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-prompt')).toBeInTheDocument());
    expect(screen.getByTestId('forge-prompt')).toHaveTextContent(/semaglutide vs tirzepatide/);
    expect(screen.getByTestId('forge-option-efficacy')).toBeInTheDocument();
    expect(screen.getByTestId('forge-option-safety')).toBeInTheDocument();
    // scoreboard renders
    expect(screen.getByTestId('forge-scoreboard')).toBeInTheDocument();
  });

  it('picks a dimension into the ranking and submits with ranking[0] as top', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    (forgeApi.submitAnswer as any).mockResolvedValue(makeResult());
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-option-efficacy')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-option-efficacy'));
    expect(screen.getByTestId('forge-ranked-efficacy')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('forge-submit'));
    await waitFor(() => expect(forgeApi.submitAnswer).toHaveBeenCalled());
    expect(forgeApi.submitAnswer).toHaveBeenCalledWith(
      'r-1',
      { selected: ['efficacy'], ranking: ['efficacy'] },
    );
  });

  it('shows the PROMOTED result with points and version', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    (forgeApi.submitAnswer as any).mockResolvedValue(makeResult());
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-option-efficacy')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-option-efficacy'));
    fireEvent.click(screen.getByTestId('forge-submit'));

    await waitFor(() => expect(screen.getByTestId('forge-result')).toBeInTheDocument());
    expect(screen.getByTestId('forge-result-state')).toHaveTextContent(/Promoted/);
    expect(screen.getByTestId('forge-points')).toHaveTextContent('+10');
    expect(screen.getByTestId('forge-result')).toHaveTextContent(/v3/);
    expect(screen.getByTestId('forge-consensus-count')).toHaveTextContent('2 / 2');
  });

  it('shows the FLAGGED state for a valid-but-not-corroborated answer', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    (forgeApi.submitAnswer as any).mockResolvedValue(makeResult({
      consensus: { state: 'flagged', agree_count: 1, threshold: 2 },
      playbook_version: null,
      score: { points: 3, reason: 'valid gold label; awaiting consensus' },
    }));
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-option-safety')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-option-safety'));
    fireEvent.click(screen.getByTestId('forge-submit'));

    await waitFor(() => expect(screen.getByTestId('forge-result-state')).toHaveTextContent(/Flagged/));
    expect(screen.getByTestId('forge-points')).toHaveTextContent('+3');
  });

  it('shows the INVALID state with validation errors and zero points', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    (forgeApi.submitAnswer as any).mockResolvedValue(makeResult({
      validation: { valid: false, errors: ['route does not resolve to a predicate'] },
      consensus: { state: 'flagged', agree_count: 1, threshold: 2 },
      playbook_version: null,
      score: { points: 0, reason: 'invalid: dimension did not validate' },
    }));
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-option-efficacy')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-option-efficacy'));
    fireEvent.click(screen.getByTestId('forge-submit'));

    await waitFor(() => expect(screen.getByTestId('forge-result-state')).toHaveTextContent(/Not validated/));
    expect(screen.getByTestId('forge-points')).toHaveTextContent('+0');
    expect(screen.getByTestId('forge-validation-errors')).toHaveTextContent(/route does not resolve/);
  });

  it('reorders ranked picks so ranking[0] reflects the top choice', async () => {
    (forgeApi.createRound as any).mockResolvedValue(makeRound());
    (forgeApi.submitAnswer as any).mockResolvedValue(makeResult());
    render(<ForgeRoundView sessionId="s-1" />);

    await waitFor(() => expect(screen.getByTestId('forge-option-efficacy')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-option-efficacy')); // rank 1
    fireEvent.click(screen.getByTestId('forge-option-safety'));   // rank 2
    // promote safety to the top
    fireEvent.click(screen.getByTestId('forge-up-safety'));
    fireEvent.click(screen.getByTestId('forge-submit'));

    await waitFor(() => expect(forgeApi.submitAnswer).toHaveBeenCalled());
    expect(forgeApi.submitAnswer).toHaveBeenCalledWith(
      'r-1',
      { selected: ['safety', 'efficacy'], ranking: ['safety', 'efficacy'] },
    );
  });

  it('shows an error with retry when the round fails to load', async () => {
    (forgeApi.createRound as any).mockRejectedValue(new Error('500: boom'));
    render(<ForgeRoundView sessionId="s-1" />);
    await waitFor(() => expect(screen.getByTestId('forge-error')).toBeInTheDocument());
    expect(screen.getByTestId('forge-retry')).toBeInTheDocument();
  });
});
