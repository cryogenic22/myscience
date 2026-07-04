import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ChatPanel from '../chat/ChatPanel';

// framer-motion → plain divs (jsdom has no layout animation).
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, exit, layout, whileHover, whileTap, ...rest } = props;
      return <div {...rest}>{children}</div>;
    },
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

describe('ChatPanel a11y', () => {
  it('the chat input textarea has an accessible name (placeholder is not one)', () => {
    render(<ChatPanel messages={[]} onSend={vi.fn()} isLoading={false} />);
    // The single most-used control in the app must be reachable by name.
    expect(screen.getByRole('textbox', { name: /ask a question/i })).toBeInTheDocument();
  });
});
