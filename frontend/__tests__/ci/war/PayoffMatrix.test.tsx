import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PayoffMatrix from '../../../src/components/ci/war/PayoffMatrix';
import type { PayoffMatrix as PayoffMatrixT } from '../../../src/types/payoff';

const MOCK_MATRIX: PayoffMatrixT = {
  room_id: 'room-1',
  rows: [
    { id: 'r1', label: 'Lilly defends' },
    { id: 'r2', label: 'Lilly cedes' },
  ],
  cols: [
    { id: 'c1', label: 'We launch Q3' },
    { id: 'c2', label: 'We wait Q4' },
  ],
  cells: [
    { row_id: 'r1', col_id: 'c1', outcome: 'lose',    delta_pct: -8.0, confidence: 0.72 },
    { row_id: 'r1', col_id: 'c2', outcome: 'neutral', delta_pct: -1.5, confidence: 0.65 },
    { row_id: 'r2', col_id: 'c1', outcome: 'win',     delta_pct: 12.0, confidence: 0.84 },
    { row_id: 'r2', col_id: 'c2', outcome: 'win',     delta_pct: 6.0,  confidence: 0.79 },
  ],
  recommended_cell: { row_id: 'r2', col_id: 'c1' },
};

describe('PayoffMatrix (PB-501)', () => {
  it('renders the matrix heading with the room id', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    expect(screen.getByRole('heading', { name: /payoff matrix/i })).toBeDefined();
  });

  it('renders all row and column labels exactly once', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    expect(screen.getAllByText('Lilly defends').length).toBe(1);
    expect(screen.getAllByText('Lilly cedes').length).toBe(1);
    expect(screen.getAllByText('We launch Q3').length).toBe(1);
    expect(screen.getAllByText('We wait Q4').length).toBe(1);
  });

  it('renders delta% with sign for each cell', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    expect(screen.getByText('+12.0%')).toBeDefined();
    expect(screen.getByText('+6.0%')).toBeDefined();
    expect(screen.getByText('-8.0%')).toBeDefined();
    expect(screen.getByText('-1.5%')).toBeDefined();
  });

  it('renders confidence as a percentage for each cell', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    expect(screen.getByText(/84% conf/i)).toBeDefined();
    expect(screen.getByText(/72% conf/i)).toBeDefined();
  });

  it('marks each cell with the outcome tier via data-outcome attribute', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    const cells = document.querySelectorAll('[data-outcome]');
    expect(cells.length).toBe(4);
    const outcomes = Array.from(cells).map((c) => c.getAttribute('data-outcome'));
    expect(outcomes.sort()).toEqual(['lose', 'neutral', 'win', 'win']);
  });

  it('marks the recommended cell so the eye finds it first', () => {
    render(<PayoffMatrix matrix={MOCK_MATRIX} />);
    const recommended = document.querySelector('[data-recommended="true"]');
    expect(recommended).not.toBeNull();
    expect(within(recommended as HTMLElement).getByText('+12.0%')).toBeDefined();
    expect(within(recommended as HTMLElement).getByText(/recommended/i)).toBeDefined();
  });

  it('renders the empty-state message when the matrix has zero cells', () => {
    const empty: PayoffMatrixT = {
      room_id: 'room-empty',
      rows: [],
      cols: [],
      cells: [],
      recommended_cell: null,
    };
    render(<PayoffMatrix matrix={empty} />);
    expect(screen.getByText(/no scenarios yet/i)).toBeDefined();
  });
});
