import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConfidenceBadge } from '../../src/components/primitives/ConfidenceBadge';

describe('ConfidenceBadge', () => {
  it('renders percentage and correct semantic color', () => {
    const { container, rerender } = render(<ConfidenceBadge value={0.3} />);
    expect(screen.getByText('30%')).toBeDefined();
    expect(container.querySelector('[data-semantic-color="red"]')).toBeDefined();

    rerender(<ConfidenceBadge value={0.7} />);
    expect(screen.getByText('70%')).toBeDefined();
    expect(container.querySelector('[data-semantic-color="amber"]')).toBeDefined();

    rerender(<ConfidenceBadge value={0.9} />);
    expect(screen.getByText('90%')).toBeDefined();
    expect(container.querySelector('[data-semantic-color="green"]')).toBeDefined();
  });
});
