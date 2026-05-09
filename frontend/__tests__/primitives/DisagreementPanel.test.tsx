import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DisagreementPanel } from '../../src/components/primitives/DisagreementPanel';

describe('DisagreementPanel', () => {
  const sources = [
    { id: '1', name: 'ClinicalTrials.gov', claim: 'Trial is Active', qualityScore: 98 },
    { id: '2', name: 'Company PR', claim: 'Trial is Suspended', qualityScore: 85 }
  ];

  it('renders conflicting sources side by side', () => {
    render(<DisagreementPanel topic="Trial Status" options={sources} onResolve={() => {}} />);
    expect(screen.getByText(/"Trial is Active"/)).toBeDefined();
    expect(screen.getByText(/"Trial is Suspended"/)).toBeDefined();
  });

  it('calls onResolve with the selected source id', () => {
    const handleResolve = vi.fn();
    render(<DisagreementPanel topic="Trial Status" options={sources} onResolve={handleResolve} />);
    
    // Click the button for the first source
    const resolveButtons = screen.getAllByRole('button', { name: /accept/i });
    fireEvent.click(resolveButtons[0]);

    expect(handleResolve).toHaveBeenCalledWith('1');
  });
});
