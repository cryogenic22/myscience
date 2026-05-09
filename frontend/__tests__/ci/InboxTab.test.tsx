import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import InboxTab from '../../src/components/ci/InboxTab';

describe('InboxTab', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('renders a Log In button when unauthenticated', () => {
    // Render with dummy props
    render(
      <InboxTab 
        onOpenDecision={() => {}} 
        onOpenWarRoom={() => {}} 
        onOpenSignals={() => {}} 
        onOpenInsights={() => {}} 
      />
    );

    // Verify the login wall message exists
    expect(screen.getByText('Log in (viewer or above) to see your decision inbox.')).toBeDefined();

    // Verify the CTA button exists (this will fail without the fix)
    const button = screen.getByRole('button', { name: /log in/i });
    expect(button).toBeDefined();
    expect(button.className).toContain('btn-primary');
  });
});
