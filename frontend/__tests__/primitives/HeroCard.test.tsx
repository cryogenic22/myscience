import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HeroCard } from '../../src/components/primitives/HeroCard';

describe('HeroCard', () => {
  it('renders children correctly', () => {
    render(
      <HeroCard>
        <div data-testid="child">Child Content</div>
      </HeroCard>
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders a title if provided', () => {
    render(<HeroCard title="Top Threat">Content</HeroCard>);
    expect(screen.getByText('Top Threat')).toBeDefined();
  });
});
