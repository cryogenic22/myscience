import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Sparkline } from '../../src/components/primitives/Sparkline';

describe('Sparkline', () => {
  it('renders null when data is empty or too small', () => {
    const { container } = render(<Sparkline data={[]} />);
    expect(container.querySelector('svg')).toBeNull();

    const singleRender = render(<Sparkline data={[10]} />);
    expect(singleRender.container.querySelector('svg')).toBeNull();
  });

  it('renders an SVG path with valid data', () => {
    const { container } = render(<Sparkline data={[10, 20, 15, 30]} />);
    const path = container.querySelector('path');
    expect(path).toBeDefined();
    expect(path?.getAttribute('d')).toContain('M');
  });

  it('renders specific color based on trend (up/down)', () => {
    // Upward trend
    const upRender = render(<Sparkline data={[10, 20, 30]} />);
    expect(upRender.container.querySelector('[data-semantic-color="green"]')).toBeDefined();

    // Downward trend
    const downRender = render(<Sparkline data={[30, 20, 10]} />);
    expect(downRender.container.querySelector('[data-semantic-color="red"]')).toBeDefined();
  });
});
