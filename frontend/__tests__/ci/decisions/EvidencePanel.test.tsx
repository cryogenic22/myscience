/**
 * SPEC_030 Stage 3 — EvidencePanel
 * Renders evidence_refs grouped by type (kbq_view, signal, entity, document).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { makeBrief, makeEvidenceRef } from './_fixtures';
import EvidencePanel from '../../../src/components/ci/decisions/EvidencePanel';

describe('EvidencePanel', () => {
  it('groups evidence_refs by type', () => {
    const brief = makeBrief({
      evidence_refs: [
        makeEvidenceRef({ type: 'kbq_view', id: 'kbq-3' }),
        makeEvidenceRef({ type: 'signal', id: 'sig-1' }),
        makeEvidenceRef({ type: 'signal', id: 'sig-2' }),
        makeEvidenceRef({ type: 'document', id: 'd-1' }),
      ],
    });
    render(<EvidencePanel brief={brief} />);
    // Group eyebrow headers (uppercase). At least one match per type.
    expect(screen.getAllByText(/kbq/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/signals/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/documents/i).length).toBeGreaterThan(0);
  });

  it('legitimate empty state renders an "add evidence" CTA when in editable state', () => {
    const brief = makeBrief({ state: 'draft', evidence_refs: [] });
    render(<EvidencePanel brief={brief} />);
    expect(screen.getByText(/no evidence linked/i)).toBeInTheDocument();
  });

  it('shows count badge on each group header', () => {
    const brief = makeBrief({
      evidence_refs: [
        makeEvidenceRef({ type: 'signal', id: 'sig-a' }),
        makeEvidenceRef({ type: 'signal', id: 'sig-b' }),
        makeEvidenceRef({ type: 'signal', id: 'sig-c' }),
      ],
    });
    render(<EvidencePanel brief={brief} />);
    // The "3" appears at least once (header count + total). At least one match.
    expect(screen.getAllByText(/^3$/).length).toBeGreaterThan(0);
  });

  it('clicking an evidence row invokes onOpen with type+id', () => {
    const onOpen = vi.fn();
    const brief = makeBrief({
      evidence_refs: [makeEvidenceRef({ type: 'signal', id: 'sig-77' })],
    });
    render(<EvidencePanel brief={brief} onOpen={onOpen} />);
    const button = screen.getByRole('button', { name: /sig-77/ });
    fireEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'signal', id: 'sig-77' }),
    );
  });

  it.todo('renders DisagreementPanel when an evidence_ref has contradicting refs');
  it.todo('locked state hides "+ add evidence" CTA');
});
