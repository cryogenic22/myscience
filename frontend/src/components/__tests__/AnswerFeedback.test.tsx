import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import NarrativeMessage from '../chat/NarrativeMessage';
import type { Message } from '../ChatMessage';

// Framer-motion minimal mock — render children without animation.
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, ...domProps } = props;
      void initial; void animate; void transition;
      return <div {...domProps}>{children}</div>;
    },
  },
}));

// Mock the API module so chatFeedback is observable.
const chatFeedback = vi.fn((arg: unknown) => {
  void arg;
  return Promise.resolve({ feedback: { id: 'fb-1', rating: 1 } });
});
vi.mock('../../api', () => ({
  api: { chatFeedback: (arg: unknown) => chatFeedback(arg) },
}));

function assistantMsg(content = 'Semaglutide reduces A1c by 1.5%.'): Message {
  return { id: 'm1', role: 'assistant', content, timestamp: new Date(), intent: 'compare' };
}

describe('NarrativeMessage — C2 answer feedback', () => {
  beforeEach(() => chatFeedback.mockClear());

  it('renders thumbs controls when a question is present', () => {
    render(<NarrativeMessage message={assistantMsg()} isUser={false} question="How well does it work?" />);
    expect(screen.getByTestId('feedback-up')).toBeInTheDocument();
    expect(screen.getByTestId('feedback-down')).toBeInTheDocument();
  });

  it('does not render feedback without a question', () => {
    render(<NarrativeMessage message={assistantMsg()} isUser={false} />);
    expect(screen.queryByTestId('answer-feedback')).toBeNull();
  });

  it('does not render feedback on user messages', () => {
    const msg = assistantMsg();
    msg.role = 'user';
    render(<NarrativeMessage message={msg} isUser={true} question="q" />);
    expect(screen.queryByTestId('answer-feedback')).toBeNull();
  });

  it('clicking thumbs up fires the API with rating +1 and the question', () => {
    render(<NarrativeMessage message={assistantMsg('answer text')} isUser={false} question="my question" />);
    fireEvent.click(screen.getByTestId('feedback-up'));
    expect(chatFeedback).toHaveBeenCalledTimes(1);
    expect(chatFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ question: 'my question', rating: 1, intent: 'compare', answerExcerpt: 'answer text' }),
    );
    expect(screen.getByTestId('feedback-thanks')).toBeInTheDocument();
  });

  it('clicking thumbs down fires the API with rating -1', () => {
    render(<NarrativeMessage message={assistantMsg()} isUser={false} question="q2" />);
    fireEvent.click(screen.getByTestId('feedback-down'));
    expect(chatFeedback).toHaveBeenCalledTimes(1);
    expect(chatFeedback).toHaveBeenCalledWith(expect.objectContaining({ question: 'q2', rating: -1 }));
  });

  it('does not double-submit once a rating is recorded', () => {
    render(<NarrativeMessage message={assistantMsg()} isUser={false} question="q3" />);
    const up = screen.getByTestId('feedback-up');
    fireEvent.click(up);
    fireEvent.click(up);
    fireEvent.click(screen.getByTestId('feedback-down'));
    expect(chatFeedback).toHaveBeenCalledTimes(1);
  });
});
