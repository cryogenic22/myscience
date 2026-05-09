/**
 * SPEC_030 Stage 3 — BriefEditableField
 *
 * Inline-edit primitive used by BriefPanel for question, success_criteria,
 * stakeholders chips, etc. Stripe-Dashboard-style: faint underline on hover,
 * expands to input on click, save on blur.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BriefEditableField from '../../../src/components/ci/decisions/BriefEditableField';

describe('BriefEditableField', () => {
  it('renders value as static text by default', () => {
    render(<BriefEditableField label="question" value="What now?" onSave={vi.fn()} />);
    expect(screen.getByText('What now?')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('clicking text reveals an input pre-populated with current value', async () => {
    render(<BriefEditableField label="question" value="What now?" onSave={vi.fn()} />);
    fireEvent.click(screen.getByText('What now?'));
    const input = await screen.findByRole('textbox');
    expect(input).toHaveValue('What now?');
  });

  it('blur after edit calls onSave with new value', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    fireEvent.click(screen.getByText('A'));
    const input = await screen.findByRole('textbox');
    fireEvent.change(input, { target: { value: 'B' } });
    fireEvent.blur(input);
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('B'));
  });

  it('blur with no change does NOT call onSave', async () => {
    const onSave = vi.fn();
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    fireEvent.click(screen.getByText('A'));
    const input = await screen.findByRole('textbox');
    fireEvent.blur(input);
    expect(onSave).not.toHaveBeenCalled();
  });

  it('locked=true prevents click-to-edit', () => {
    render(<BriefEditableField label="question" value="A" onSave={vi.fn()} locked />);
    fireEvent.click(screen.getByText('A'));
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('escape during edit reverts and exits without save', async () => {
    const onSave = vi.fn();
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    fireEvent.click(screen.getByText('A'));
    const input = await screen.findByRole('textbox');
    fireEvent.change(input, { target: { value: 'B' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('shows busy spinner overlay while save is in flight', async () => {
    let resolve: (v: void) => void = () => {};
    const onSave = vi.fn().mockImplementation(
      () => new Promise<void>((r) => { resolve = r; }),
    );
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    fireEvent.click(screen.getByText('A'));
    const input = await screen.findByRole('textbox');
    fireEvent.change(input, { target: { value: 'B' } });
    fireEvent.blur(input);
    // Saving indicator visible
    expect(await screen.findByLabelText(/saving/i)).toBeInTheDocument();
    resolve();
  });

  it.todo('on save error, reverts to old value and surfaces toast');
});
