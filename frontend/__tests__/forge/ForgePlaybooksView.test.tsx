/**
 * DF — ForgePlaybooksView tests.
 *
 * Covers the authoring browse: the playbook list renders with source badges,
 * opening a DB-backed playbook loads its version history, rollback fires the
 * API, and a seed playbook shows the read-only note (no rollback).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  playbooksApi: { list: vi.fn(), versions: vi.fn(), rollback: vi.fn() },
}));

import { playbooksApi } from '../../src/api';
import ForgePlaybooksView from '../../src/components/forge/ForgePlaybooksView';

const DB_PB = {
  playbook: {
    id: 'compare.drug_x_drug', pack: 'pharma', trigger: {}, synthesis: {},
    dimensions: [{ key: 'efficacy', label: 'Efficacy', sub_question: '', routes: ['predicate:trial_result'], required: false, weight: 0.7 }],
  },
  meta: { version: 3, author: 'sme-1', active: true },
  source: 'db' as const,
};

const SEED_PB = {
  playbook: { id: 'compare.seed_only', pack: 'pharma', trigger: {}, synthesis: {}, dimensions: [] },
  meta: { version: null, author: null, active: true },
  source: 'seed' as const,
};

describe('ForgePlaybooksView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (playbooksApi.versions as any).mockResolvedValue([
      { version: 3, action: 'update', snapshot: DB_PB.playbook, diff: {}, author: 'sme-1', note: 'added efficacy', rolled_back_from: null, created_at: null },
      { version: 2, action: 'update', snapshot: DB_PB.playbook, diff: {}, author: 'sme-1', note: 'added safety', rolled_back_from: null, created_at: null },
      { version: 1, action: 'create', snapshot: DB_PB.playbook, diff: {}, author: 'sme-1', note: null, rolled_back_from: null, created_at: null },
    ]);
  });

  it('lists playbooks with their source badges', async () => {
    (playbooksApi.list as any).mockResolvedValue([DB_PB, SEED_PB]);
    render(<ForgePlaybooksView />);

    await waitFor(() => expect(screen.getByTestId('forge-playbook-compare.drug_x_drug')).toBeInTheDocument());
    expect(screen.getByTestId('forge-playbook-compare.seed_only')).toBeInTheDocument();
  });

  it('opens a DB-backed playbook and loads its version history', async () => {
    (playbooksApi.list as any).mockResolvedValue([DB_PB]);
    render(<ForgePlaybooksView />);

    await waitFor(() => expect(screen.getByTestId('forge-playbook-toggle-compare.drug_x_drug')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-playbook-toggle-compare.drug_x_drug'));

    await waitFor(() => expect(screen.getByTestId('forge-version-compare.drug_x_drug-3')).toBeInTheDocument());
    expect(screen.getByTestId('forge-version-compare.drug_x_drug-1')).toBeInTheDocument();
    // current version has no restore button; prior versions do.
    expect(screen.queryByTestId('forge-rollback-compare.drug_x_drug-3')).not.toBeInTheDocument();
    expect(screen.getByTestId('forge-rollback-compare.drug_x_drug-1')).toBeInTheDocument();
  });

  it('rolls back to a prior version', async () => {
    (playbooksApi.list as any).mockResolvedValue([DB_PB]);
    (playbooksApi.rollback as any).mockResolvedValue({ playbook: DB_PB.playbook, meta: { version: 4 } });
    render(<ForgePlaybooksView />);

    await waitFor(() => expect(screen.getByTestId('forge-playbook-toggle-compare.drug_x_drug')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-playbook-toggle-compare.drug_x_drug'));
    await waitFor(() => expect(screen.getByTestId('forge-rollback-compare.drug_x_drug-1')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('forge-rollback-compare.drug_x_drug-1'));
    await waitFor(() => expect(playbooksApi.rollback).toHaveBeenCalledWith('compare.drug_x_drug', 1, expect.any(String)));
  });

  it('shows the read-only note for a seed playbook (no rollback)', async () => {
    (playbooksApi.list as any).mockResolvedValue([SEED_PB]);
    render(<ForgePlaybooksView />);

    await waitFor(() => expect(screen.getByTestId('forge-playbook-toggle-compare.seed_only')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('forge-playbook-toggle-compare.seed_only'));
    await waitFor(() => expect(screen.getByTestId('forge-playbook-seed-note-compare.seed_only')).toBeInTheDocument());
    expect(screen.queryByTestId('forge-versions-compare.seed_only')).not.toBeInTheDocument();
  });

  it('shows an error when the list fails', async () => {
    (playbooksApi.list as any).mockRejectedValue(new Error('500: boom'));
    render(<ForgePlaybooksView />);
    await waitFor(() => expect(screen.getByTestId('forge-playbooks-error')).toBeInTheDocument());
  });
});
