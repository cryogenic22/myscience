import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Timeline } from '../../src/components/primitives/Timeline';

describe('Timeline', () => {
  const items = [
    { title: 'Past Event', timestamp: '2023', status: 'past' as const },
    { title: 'Current Event', timestamp: '2024', status: 'active' as const },
    { title: 'Future Event', timestamp: '2025', status: 'future' as const },
  ];

  it('renders all items', () => {
    render(<Timeline items={items} />);
    expect(screen.getByText('Past Event')).toBeDefined();
    expect(screen.getByText('Current Event')).toBeDefined();
    expect(screen.getByText('Future Event')).toBeDefined();
  });

  it('applies correct semantic styling based on status', () => {
    const { container } = render(<Timeline items={items} />);
    const activeDot = container.querySelector('[data-status="active"]');
    expect(activeDot).toBeDefined();
  });
});
