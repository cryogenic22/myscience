import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import GraphContextMenu from '../graph/GraphContextMenu';
import type { GraphNode } from '../../api';

const MOCK_NODE: GraphNode = {
  entity_id: 'drug-123',
  entity_type: 'drug',
  label: 'Semaglutide',
  properties: {},
};

const DEFAULT_POSITION = { x: 200, y: 300 };

function renderMenu(overrides: Partial<Parameters<typeof GraphContextMenu>[0]> = {}) {
  const onAskInChat = vi.fn();
  const onClose = vi.fn();
  const result = render(
    <GraphContextMenu
      node={MOCK_NODE}
      position={DEFAULT_POSITION}
      onAskInChat={onAskInChat}
      onClose={onClose}
      {...overrides}
    />,
  );
  return { onAskInChat, onClose, ...result };
}

describe('GraphContextMenu', () => {
  it('renders with 3 menu items', () => {
    renderMenu();
    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(3);
  });

  it('displays correct labels including node name', () => {
    renderMenu();
    expect(screen.getByText('Ask about Semaglutide')).toBeTruthy();
    expect(screen.getByText('Generate dossier')).toBeTruthy();
    expect(screen.getByText(/Compare with/)).toBeTruthy();
  });

  it('clicking "Ask about" calls onAskInChat with correct question', () => {
    const { onAskInChat, onClose } = renderMenu();
    fireEvent.click(screen.getByTestId('graph-context-menu-ask'));
    expect(onAskInChat).toHaveBeenCalledWith('Tell me about Semaglutide');
    expect(onClose).toHaveBeenCalled();
  });

  it('clicking "Generate dossier" calls onAskInChat with dossier question', () => {
    const { onAskInChat, onClose } = renderMenu();
    fireEvent.click(screen.getByTestId('graph-context-menu-dossier'));
    expect(onAskInChat).toHaveBeenCalledWith('Generate a dossier on Semaglutide');
    expect(onClose).toHaveBeenCalled();
  });

  it('clicking "Compare with..." calls onAskInChat with compare prefix', () => {
    const { onAskInChat, onClose } = renderMenu();
    fireEvent.click(screen.getByTestId('graph-context-menu-compare'));
    expect(onAskInChat).toHaveBeenCalledWith('Compare Semaglutide with ');
    expect(onClose).toHaveBeenCalled();
  });

  it('is dismissed on Escape key', () => {
    const { onClose } = renderMenu();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('is dismissed on click outside', async () => {
    const { onClose } = renderMenu();
    // The component uses setTimeout(0) before attaching the listener,
    // so we need to advance timers
    await vi.waitFor(() => {
      fireEvent.mouseDown(document.body);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('renders at the specified position', () => {
    renderMenu({ position: { x: 400, y: 500 } });
    const menu = screen.getByTestId('graph-context-menu');
    expect(menu.style.left).toBe('400px');
    expect(menu.style.top).toBe('500px');
  });
});
