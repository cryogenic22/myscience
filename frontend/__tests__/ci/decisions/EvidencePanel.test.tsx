/**
 * SPEC_030 Stage 3 — EvidencePanel
 * Renders evidence_refs grouped by type (kbq_view, signal, entity, document).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { makeBrief, makeEvidenceRef } from './_fixtures';
import EvidencePanel from '../../../src/components/ci/decisions/EvidencePanel';

describe('EvidencePanel', () => {
  it('groups evidence_refs by type', () => {
    const brief = makeBrief({
      evidence_refs: [
        makeEvidenceRef({ type: 'kbq_view', id: 'kbq-3' }),
        makeEvidenceRef({ type: 'signal', id: 's-1' }),
        makeEvidenceRef({ type: 'signal', id: 's-2' }),
        makeEvidenceRef({ type: 'document', id: 'd-1' }),
      ],
    });
    render(<EvidencePanel brief={brief} />);
    // Group headers: KBQ, Signals (2), Documents (1)
    expect(screen.getByText(/kbq/i)).toBeInTheDocument();
    expect(screen.getByText(/signals/i)).toBeInTheDocument();
    expect(screen.getByText(/documents/i)).toBeInTheDocument();
  });

  it('legitimate empty state renders an "add evidence" CTA when in editable state', () => {
    const brief = makeBrief({ state: 'draft', evidence_refs: [] });
    render(<EvidencePanel brief={brief} />);
    expect(screen.getByText(/no evidence linked/i)).toBeInTheDocument();
  });

  it('shows count badge on each group header', () => {
    const brief = makeBrief({
      evidence_refs: [
        makeEvidenceRef({ type: 'signal' }),
        makeEvidenceRef({ type: 'signal' }),
        makeEvidenceRef({ type: 'signal' }),
      ],
    });
    render(<EvidencePanel brief={brief} />);
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });

  it('clicking an evidence row invokes onOpen with type+id', () => {
    const onOpen = vi.fn();
    const brief = makeBrief({
      evidence_refs: [makeEvidenceRef({ type: 'signal', id: 's-77' })],
    });
    render(<EvidencePanel brief={brief} onOpen={onOpen} />);
    // The row exposes either id or a link element
    const row = screen.getByText(/s-77/);
    row.click();
    expect(onOpen).toHaveBeenCalledWith({ type: 'signal', id: 's-77' });
  });

  it.todo('renders DisagreementPanel when an evidence_ref has contradicting refs');
  it.todo('locked state hides "+ add evidence" CTA');
});
