import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ConnectorSummary, ConnectorDetail } from '../../api';
import ConnectorsPage from '../ConnectorsPage';

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const mockList = vi.fn();
const mockDetail = vi.fn();
vi.mock('../../api', () => ({
  connectorsApi: {
    list: (...a: unknown[]) => mockList(...a),
    detail: (...a: unknown[]) => mockDetail(...a),
  },
}));

// The detail view is heavy (tabs + sub-fetches); stub it so these tests target
// ConnectorsPage's own error routing, not the detail internals.
vi.mock('../../components/connectors/ConnectorDetail', () => ({
  default: ({ detail }: { detail: { label: string } }) => (
    <div data-testid="detail-view">{detail.label}</div>
  ),
}));

const mk = (source_key: string, label: string, status: ConnectorSummary['connection_status']): ConnectorSummary => ({
  source_key,
  label,
  schedule: 'daily',
  enabled: true,
  auto_approve_runs: false,
  manual_only: false,
  notes: null,
  connection_status: status,
  last_run: null,
  description: null,
  license: null,
});

const CTGOV = mk('ctgov', 'ClinicalTrials.gov', 'connected');
const PUBMED = mk('pubmed', 'PubMed', 'available');
const detailFor = (s: ConnectorSummary): ConnectorDetail => ({
  ...s,
  license_url: null,
  api_base_url: null,
  config: { enabled: true, auto_approve_runs: false, manual_only: false, notes: null },
  recent_runs: [],
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ConnectorsPage', () => {
  it('a detail-fetch failure does NOT blank the working list (no error blast-radius)', async () => {
    mockList.mockResolvedValue({ connectors: [CTGOV, PUBMED] });
    mockDetail.mockRejectedValue(new Error('detail 500'));

    render(<ConnectorsPage />);

    // The detail error must be scoped to the detail pane...
    const err = await screen.findByTestId('detail-error');
    expect(within(err).getByRole('button', { name: /retry/i })).toBeInTheDocument();

    // ...and the connector list must still be rendered (previously a detail 500
    // set the top-level error and replaced the whole page).
    expect(screen.getByText('ClinicalTrials.gov')).toBeInTheDocument();
    expect(screen.getByText('PubMed')).toBeInTheDocument();
  });

  it('a list-load failure shows an honest error with a working Retry', async () => {
    mockList
      .mockRejectedValueOnce(new Error('list 500'))
      .mockResolvedValueOnce({ connectors: [CTGOV, PUBMED] });
    mockDetail.mockResolvedValue(detailFor(CTGOV));

    render(<ConnectorsPage />);

    const err = await screen.findByTestId('list-error');
    fireEvent.click(within(err).getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByText('ClinicalTrials.gov')).toBeInTheDocument());
    // The stale error must be cleared after a successful reload.
    expect(screen.queryByTestId('list-error')).not.toBeInTheDocument();
  });

  it('recovers the detail pane when a failed detail load is retried', async () => {
    mockList.mockResolvedValue({ connectors: [CTGOV, PUBMED] });
    mockDetail
      .mockRejectedValueOnce(new Error('detail 500'))
      .mockResolvedValueOnce(detailFor(CTGOV));

    render(<ConnectorsPage />);

    const err = await screen.findByTestId('detail-error');
    fireEvent.click(within(err).getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByTestId('detail-view')).toHaveTextContent('ClinicalTrials.gov'));
    expect(screen.queryByTestId('detail-error')).not.toBeInTheDocument();
  });
});
