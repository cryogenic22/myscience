import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-full transition-colors flex items-center justify-center cursor-pointer"
      style={{
        background: 'var(--color-surface-2)',
        color: 'var(--color-ink-3)',
      }}
      title="Toggle Theme"
      aria-label="Toggle Theme"
    >
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
