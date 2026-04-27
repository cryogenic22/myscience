import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { Card } from './Card';

describe('Card', () => {
  it('renders children', () => {
    render(<Card>hello</Card>);
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('flat variant has no role=button', () => {
    render(<Card>flat</Card>);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('interactive variant exposes button role + responds to Enter', () => {
    const onClick = vi.fn();
    render(<Card variant="interactive" onClick={onClick}>x</Card>);
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyDown(btn, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(3);
  });

  it('elevated variant uses elevated background token', () => {
    render(<Card variant="elevated" data-testid="c">e</Card>);
    const el = screen.getByTestId('c');
    expect(el.style.background).toContain('--mz-color-elevated');
  });
});
