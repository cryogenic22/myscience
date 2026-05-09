import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EvidenceAffordance } from '../../src/components/primitives/EvidenceAffordance';

describe('EvidenceAffordance', () => {
  it('renders a button and opens a panel on click', () => {
    const mockEvidence = {
      source: 'ClinicalTrials.gov',
      timestamp: '2026-05-01',
      passage: 'The trial met its primary endpoint.',
    };

    render(<EvidenceAffordance claimId="123" evidenceData={mockEvidence} />);
    
    // initially not visible
    expect(screen.queryByText('The trial met its primary endpoint.')).toBeNull();

    // click button
    const button = screen.getByRole('button', { name: /view evidence/i });
    fireEvent.click(button);

    // panel visible
    expect(screen.getByText(/"The trial met its primary endpoint."/)).toBeDefined();
    expect(screen.getByText('ClinicalTrials.gov')).toBeDefined();
  });
});
