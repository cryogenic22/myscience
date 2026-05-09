import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MetricRing } from '../../src/components/primitives/MetricRing';

describe('MetricRing', () => {
  it('renders correctly with given percentage', () => {
    render(<MetricRing value={75} size={60} strokeWidth={4} />);
    const textElement = screen.getByText('75%');
    expect(textElement).toBeDefined();
  });

  it('clamps value between 0 and 100', () => {
    const { rerender } = render(<MetricRing value={-10} />);
    expect(screen.getByText('0%')).toBeDefined();

    rerender(<MetricRing value={150} />);
    expect(screen.getByText('100%')).toBeDefined();
  });

  it('renders specific color based on semantic threshold', () => {
    // We expect it to pass semantic color classes or stroke attributes
    const { container, rerender } = render(<MetricRing value={30} />);
    // 30 should be red
    expect(container.querySelector('[data-semantic-color="red"]')).toBeDefined();

    rerender(<MetricRing value={60} />);
    // 60 should be amber
    expect(container.querySelector('[data-semantic-color="amber"]')).toBeDefined();

    rerender(<MetricRing value={90} />);
    // 90 should be green
    expect(container.querySelector('[data-semantic-color="green"]')).toBeDefined();
  });
});
