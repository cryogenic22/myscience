import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

/**
 * Three themes coexist during the v7 migration:
 *   'zs'    — light foundation + orange/teal accents, the v7 design canon.
 *   'dark'  — locked war-room dark (Helix). What /ci surfaces use today.
 *   'light' — legacy white + blue accent. Deprecated as surfaces migrate to zs.
 *
 * The toggle cycles zs ↔ dark ↔ light → zs. Power users can pick directly
 * via `setTheme`.
 */
export type Theme = 'zs' | 'dark' | 'light';

export const THEMES: readonly Theme[] = ['zs', 'dark', 'light'] as const;

interface ThemeContextType {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem('mz-theme');
  if (saved === 'zs' || saved === 'dark' || saved === 'light') return saved as Theme;
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'dark'; // default fallback preserves prior behavior
}

function nextTheme(current: Theme): Theme {
  const i = THEMES.indexOf(current);
  return THEMES[(i + 1) % THEMES.length];
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark', 'zs');
    root.classList.add(theme);
    window.localStorage.setItem('mz-theme', theme);
  }, [theme]);

  const setTheme = (t: Theme) => setThemeState(t);
  const toggleTheme = () => setThemeState((prev) => nextTheme(prev));

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (ctx === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}

// Exposed for tests that don't want a ProviderHarness.
export const __test = { nextTheme, readInitialTheme };
