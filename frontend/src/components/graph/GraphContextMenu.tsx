/**
 * GraphContextMenu — Right-click context menu for graph nodes.
 *
 * Offers contextual actions that inject pre-formed questions into chat:
 * - "Ask about {label}"
 * - "Generate dossier"
 * - "Compare with..."
 */
import { useCallback, useEffect, useRef } from 'react';
import type { GraphNode } from '../../api';

export interface GraphContextMenuProps {
  node: GraphNode;
  position: { x: number; y: number };
  onAskInChat: (question: string) => void;
  onClose: () => void;
}

const MENU_ITEMS = [
  {
    id: 'ask',
    labelFn: (name: string) => `Ask about ${name}`,
    questionFn: (name: string) => `Tell me about ${name}`,
  },
  {
    id: 'dossier',
    labelFn: (_name: string) => `Generate dossier`,
    questionFn: (name: string) => `Generate a dossier on ${name}`,
  },
  {
    id: 'compare',
    labelFn: (_name: string) => `Compare with\u2026`,
    questionFn: (name: string) => `Compare ${name} with `,
  },
] as const;

export default function GraphContextMenu({
  node,
  position,
  onAskInChat,
  onClose,
}: GraphContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Dismiss on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Use setTimeout to avoid the same right-click event immediately closing
    const timer = window.setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [onClose]);

  // Dismiss on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleItemClick = useCallback(
    (questionFn: (name: string) => string) => {
      onAskInChat(questionFn(node.label));
      onClose();
    },
    [node.label, onAskInChat, onClose],
  );

  return (
    <div
      ref={menuRef}
      role="menu"
      data-testid="graph-context-menu"
      style={{
        position: 'fixed',
        left: position.x,
        top: position.y,
        zIndex: 9999,
        background: 'var(--color-surface, #ffffff)',
        border: '1px solid var(--color-line, #e2e8f0)',
        borderRadius: '8px',
        padding: '4px',
        boxShadow: '0 4px 16px rgba(0, 0, 0, 0.12), 0 1px 3px rgba(0, 0, 0, 0.08)',
        minWidth: '180px',
      }}
    >
      {MENU_ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          data-testid={`graph-context-menu-${item.id}`}
          onClick={() => handleItemClick(item.questionFn)}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            padding: '8px 12px',
            fontSize: '12px',
            fontFamily: 'var(--font-body, "DM Sans", sans-serif)',
            color: 'var(--color-ink, #1e293b)',
            background: 'transparent',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            lineHeight: 1.4,
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background =
              'var(--color-surface-2, #f1f5f9)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
        >
          {item.labelFn(node.label)}
        </button>
      ))}
    </div>
  );
}
