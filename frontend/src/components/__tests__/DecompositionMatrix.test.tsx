import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import DecompositionMatrix from '../canvas/DecompositionMatrix';
import type { DecompositionMatrix as MatrixData } from '../../api';

function makeMatrix(overrides: Partial<MatrixData> = {}): MatrixData {
  return {
    playbook_id: 'glp1_compare',
    intent: 'compare',
    entities: [
      { entity_id: 'sema', entity_type: 'drug', label: 'Semaglutide' },
      { entity_id: 'tirz', entity_type: 'drug', label: 'Tirzepatide' },
    ],
    dimensions: [
      { key: 'efficacy', label: 'Efficacy', sub_question: 'How effective?', routes: ['predicate:clinical_trial'], required: true, weight: 0.8 },
      { key: 'pricing', label: 'Pricing', sub_question: 'What does it cost?', routes: ['predicate:wac_usd'], required: false, weight: 0.5 },
    ],
    cells: [
      {
        dimension: 'efficacy', entity_id: 'sema', sub_question: 'How effective?', coverage: 'covered',
        facts: [
          { id: 'f1', predicate: 'clinical_trial', claim: 'STEP 1: 14.9% weight loss', fact_class: 'corporate', source_label: 'fact_emitter · conf 90%', source_url: 'https://clinicaltrials.gov/NCT1', confidence: 0.9 },
          { id: 'f2', predicate: 'clinical_trial', claim: 'STEP 8: superiority vs comparator', fact_class: 'corporate', source_label: 'fact_emitter', source_url: null, confidence: 0.8 },
        ],
        routes_executed: ['predicate:clinical_trial'], routes_skipped: [],
      },
      {
        dimension: 'efficacy', entity_id: 'tirz', sub_question: 'How effective?', coverage: 'thin',
        facts: [
          { id: 'f3', predicate: 'clinical_trial', claim: 'SURMOUNT-1: 20.9% weight loss', fact_class: 'corporate', source_label: 'fact_emitter', source_url: 'https://clinicaltrials.gov/NCT2', confidence: 0.85 },
        ],
        routes_executed: ['predicate:clinical_trial'], routes_skipped: [],
      },
      {
        dimension: 'pricing', entity_id: 'sema', sub_question: 'What does it cost?', coverage: 'gap',
        facts: [], routes_executed: [], routes_skipped: ['predicate:wac_usd'],
      },
      {
        dimension: 'pricing', entity_id: 'tirz', sub_question: 'What does it cost?', coverage: 'gap',
        facts: [], routes_executed: [], routes_skipped: ['predicate:wac_usd'],
      },
    ],
    coverage_summary: { efficacy: 'covered', pricing: 'gap' },
    gaps: ['pricing'],
    synthesis: {},
    ...overrides,
  };
}

describe('DecompositionMatrix', () => {
  it('renders entity columns and dimension rows', () => {
    render(<DecompositionMatrix matrix={makeMatrix()} />);
    expect(screen.getByText('Semaglutide')).toBeInTheDocument();
    expect(screen.getByText('Tirzepatide')).toBeInTheDocument();
    expect(screen.getByText('Efficacy')).toBeInTheDocument();
    expect(screen.getByText('Pricing')).toBeInTheDocument();
  });

  it('renders a covered cell with its grounded claim and source link', () => {
    render(<DecompositionMatrix matrix={makeMatrix()} />);
    const cell = screen.getByTestId('matrix-cell-efficacy-sema');
    expect(within(cell).getByText(/STEP 1: 14.9% weight loss/)).toBeInTheDocument();
    expect(within(cell).getByText(/covered/i)).toBeInTheDocument();
    const link = within(cell).getByRole('link');
    expect(link).toHaveAttribute('href', 'https://clinicaltrials.gov/NCT1');
  });

  it('renders gap cells with an explicit muted "no facts in KB" message (never hidden)', () => {
    render(<DecompositionMatrix matrix={makeMatrix()} />);
    const cell = screen.getByTestId('matrix-cell-pricing-sema');
    expect(cell).toBeInTheDocument();
    expect(within(cell).getByText(/gap — no facts in KB/i)).toBeInTheDocument();
  });

  it('renders a thin cell labelled thin', () => {
    render(<DecompositionMatrix matrix={makeMatrix()} />);
    const cell = screen.getByTestId('matrix-cell-efficacy-tirz');
    expect(within(cell).getByText(/thin/i)).toBeInTheDocument();
    expect(within(cell).getByText(/SURMOUNT-1/)).toBeInTheDocument();
  });

  it('shows fact-class glyphs for grounded facts', () => {
    render(<DecompositionMatrix matrix={makeMatrix()} />);
    const cell = screen.getByTestId('matrix-cell-efficacy-sema');
    // FactClassGlyph renders an aria-labelled span for the corporate class
    expect(within(cell).getAllByLabelText(/corporate fact/i).length).toBeGreaterThan(0);
  });

  it('renders nothing when there are no dimensions', () => {
    const { container } = render(
      <DecompositionMatrix matrix={makeMatrix({ dimensions: [], cells: [] })} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
