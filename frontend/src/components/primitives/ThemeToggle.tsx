import { Moon, Sun, Sparkles } from 'lucide-react';
import { useTheme, type Theme } from '../../hooks/useTheme';

/**
 * Three-state theme toggle (zs · dark · light).
 *
 * Click cycles through the three themes in order. The icon reflects what the
 * theme IS, not what clicking it will produce — matches how OS-level toggles
 * behave and avoids the "what will this do?" guess.
 *
 *   zs    → Sparkles (the new design canon)
 *   dark  → Sun (clicking returns to light idiom)
 *   light → Moon (clicking moves toward dark idiom)
 *
 * The tooltip names the *current* theme so power users always know where
 * they are.
 */
const ICON_FOR: Record<Theme, typeof Moon> = {
  zs: Sparkles,
  dark: Sun,
  light: Moon,
};

const LABEL_FOR: Record<Theme, string> = {
  zs: 'ZS theme (light + orange/teal)',
  dark: 'Dark theme (Helix war-room)',
  light: 'Light theme (legacy)',
};

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const Icon = ICON_FOR[theme];
  const label = LABEL_FOR[theme];

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-full transition-colors flex items-center justify-center cursor-pointer"
      style={{
        background: 'var(--color-surface-2)',
        color: 'var(--color-ink-3)',
      }}
      title={`${label} · click to cycle`}
      aria-label={`Theme: ${label}. Click to cycle.`}
      data-theme-current={theme}
    >
      <Icon size={16} />
    </button>
  );
}
