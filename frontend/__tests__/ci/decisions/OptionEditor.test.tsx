/**
 * SPEC_030 Stage 3 — OptionEditor
 *
 * Modal-style editor for adding / editing / removing a brief option.
 * Validates label is non-empty before save.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import OptionEditor from '../../../src/components/ci/decisions/OptionEditor';

describe('OptionEditor', () => {
  it('renders blank inputs in "create" mode', () => {
    render(<OptionEditor mode="create" onSave={vi.fn()} onClose={vi.fn()} />);
    const labelInput = screen.getByRole('textbox', { name: /label/i }) as HTMLInputElement;
    expect(labelInput.value).toBe('');
  });

  it('pre-fills inputs in "edit" mode', () => {
    render(
      <OptionEditor
        mode="edit"
        initial={{ label: 'Hold', description: null, predicted_outcome: null, cost_estimate: null, risk_notes: null }}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const labelInput = screen.getByRole('textbox', { name: /label/i }) as HTMLInputElement;
    expect(labelInput.value).toBe('Hold');
  });

  it('disables Save when label is empty', () => {
    render(<OptionEditor mode="create" onSave={vi.fn()} onClose={vi.fn()} />);
    const saveBtn = screen.getByRole('button', { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it('Save calls onSave with all fields', async () => {
    const onSave = vi.fn().mockResolvedValue({});
    render(<OptionEditor mode="create" onSave={onSave} onClose={vi.fn()} />);
    fireEvent.change(screen.getByRole('textbox', { name: /label/i }), { target: { value: 'Hold' } });
    fireEvent.change(screen.getByRole('textbox', { name: /description/i }), { target: { value: 'Wait it out' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({ label: 'Hold', description: 'Wait it out' }),
      ),
    );
  });

  it('Cancel calls onClose without onSave', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(<OptionEditor mode="create" onSave={onSave} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('escape key invokes onClose', () => {
    const onClose = vi.fn();
    render(<OptionEditor mode="create" onSave={vi.fn()} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it.todo('"Remove" button appears in edit mode and calls onRemove');
});
