import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import KBQFilter from '../../src/components/ci/KBQFilter';

describe('KBQFilter — multi-select (PB-104)', () => {
  it('renders "All" active when selected is empty', () => {
    render(<KBQFilter selected={[]} onSelect={() => {}} />);
    const allBtn = screen.getByRole('button', { name: 'All' });
    // The active state is conveyed via background; assert via the inline style
    expect(allBtn.getAttribute('style')).toContain('var(--color-accent)');
  });

  it('renders only the selected chips as active', () => {
    render(<KBQFilter selected={['financial', 'clinical']} onSelect={() => {}} />);
    const financial = screen.getByRole('button', { name: 'Financial' });
    const clinical = screen.getByRole('button', { name: 'Clinical' });
    const regulatory = screen.getByRole('button', { name: 'Regulatory' });
    const all = screen.getByRole('button', { name: 'All' });
    expect(financial.getAttribute('style')).toContain('var(--color-accent)');
    expect(clinical.getAttribute('style')).toContain('var(--color-accent)');
    expect(regulatory.getAttribute('style')).not.toContain('background: var(--color-accent)');
    expect(all.getAttribute('style')).not.toContain('background: var(--color-accent)');
  });

  it('clicking an unselected chip ADDS it to the selection (additive, not replace)', () => {
    const onSelect = vi.fn();
    render(<KBQFilter selected={['financial']} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clinical' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    const next = onSelect.mock.calls[0][0];
    expect(next).toEqual(expect.arrayContaining(['financial', 'clinical']));
    expect(next).toHaveLength(2);
  });

  it('clicking an already-selected chip REMOVES it', () => {
    const onSelect = vi.fn();
    render(<KBQFilter selected={['financial', 'clinical']} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clinical' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toEqual(['financial']);
  });

  it('clicking the last selected chip clears the selection (empty array → "All" becomes active)', () => {
    const onSelect = vi.fn();
    render(<KBQFilter selected={['financial']} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'Financial' }));
    expect(onSelect.mock.calls[0][0]).toEqual([]);
  });

  it('clicking "All" clears every selected chip', () => {
    const onSelect = vi.fn();
    render(<KBQFilter selected={['financial', 'clinical', 'regulatory']} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toEqual([]);
  });

  it('exposes aria-pressed for each chip so screen readers track multi-select state', () => {
    render(<KBQFilter selected={['financial']} onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: 'Financial' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Clinical' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: 'All' }).getAttribute('aria-pressed')).toBe('false');
  });
});
