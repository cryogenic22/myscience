/**
 * PB-UX03 — ProvenancePanel tests.
 *
 * The trust surface: claim + confidence tier + source drill-through. Verifies
 * it renders nothing when closed, shows the source link when a fact has a
 * sourceUrl, degrades gracefully when it doesn't, and closes.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ProvenancePanel from '../../src/components/ci/ProvenancePanel';
import type { Fact } from '../../src/pages/EngagementDossierPage';

const FACT: Fact = {
  id: 'f-1',
  claim: 'Trial success rate 86%',
  factClass: 'corporate',
  sourceLabel: 'PharmaMetrics · materialized view',
  sourceUrl: 'https://api.fda.gov/drug/x',
};

describe('ProvenancePanel', () => {
  it('renders nothing when no fact is open', () => {
    const { container } = render(<ProvenancePanel fact={null} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the claim, source label, and a working drill-through link', () => {
    render(<ProvenancePanel fact={FACT} onClose={() => {}} />);
    expect(screen.getByTestId('provenance-panel')).toBeInTheDocument();
    expect(screen.getByText('Trial success rate 86%')).toBeInTheDocument();
    expect(screen.getByText(/PharmaMetrics/)).toBeInTheDocument();
    const link = screen.getByTestId('provenance-source-link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://api.fda.gov/drug/x');
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('degrades gracefully when a fact has no source link', () => {
    render(<ProvenancePanel fact={{ ...FACT, sourceUrl: undefined }} onClose={() => {}} />);
    expect(screen.queryByTestId('provenance-source-link')).not.toBeInTheDocument();
    expect(screen.getByText(/No external source link/)).toBeInTheDocument();
  });

  it('calls onClose from the close button', () => {
    const onClose = vi.fn();
    render(<ProvenancePanel fact={FACT} onClose={onClose} />);
    fireEvent.click(screen.getByTestId('provenance-close'));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
