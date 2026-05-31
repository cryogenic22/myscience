/**
 * F1 — useTheme tests.
 *
 * Three-theme support (zs / dark / light) with stable cycle order and
 * localStorage persistence. The ZS theme is the v7 design canon; dark is
 * the existing Helix war-room; light is the legacy white+blue.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { ThemeProvider, useTheme, THEMES, __test } from '../../src/hooks/useTheme';

function Harness({ onReady }: { onReady: (api: ReturnType<typeof useTheme>) => void }) {
  const api = useTheme();
  onReady(api);
  return null;
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = '';
});

describe('useTheme — three themes', () => {
  it('exposes zs / dark / light as the available set', () => {
    expect(THEMES).toEqual(['zs', 'dark', 'light']);
  });

  it('cycle order is zs → dark → light → zs', () => {
    const { nextTheme } = __test;
    expect(nextTheme('zs')).toBe('dark');
    expect(nextTheme('dark')).toBe('light');
    expect(nextTheme('light')).toBe('zs');
  });

  it('toggleTheme cycles through all three', () => {
    let api!: ReturnType<typeof useTheme>;
    render(
      <ThemeProvider>
        <Harness onReady={(a) => (api = a)} />
      </ThemeProvider>,
    );
    const first = api.theme;
    act(() => api.toggleTheme());
    const second = api.theme;
    act(() => api.toggleTheme());
    const third = api.theme;
    act(() => api.toggleTheme());
    const fourth = api.theme;
    // Each step is a distinct theme, and after three steps we return to start.
    expect(new Set([first, second, third])).toEqual(new Set(THEMES));
    expect(fourth).toBe(first);
  });

  it('setTheme(zs) directly applies the zs class to html', () => {
    let api!: ReturnType<typeof useTheme>;
    render(
      <ThemeProvider>
        <Harness onReady={(a) => (api = a)} />
      </ThemeProvider>,
    );
    act(() => api.setTheme('zs'));
    expect(document.documentElement.classList.contains('zs')).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('persists choice to localStorage', () => {
    let api!: ReturnType<typeof useTheme>;
    render(
      <ThemeProvider>
        <Harness onReady={(a) => (api = a)} />
      </ThemeProvider>,
    );
    act(() => api.setTheme('zs'));
    expect(window.localStorage.getItem('mz-theme')).toBe('zs');
  });

  it('reads saved theme on mount', () => {
    window.localStorage.setItem('mz-theme', 'zs');
    let api!: ReturnType<typeof useTheme>;
    render(
      <ThemeProvider>
        <Harness onReady={(a) => (api = a)} />
      </ThemeProvider>,
    );
    expect(api.theme).toBe('zs');
    expect(document.documentElement.classList.contains('zs')).toBe(true);
  });

  it('useTheme outside provider throws a clear error', () => {
    // Suppress React error boundary console noise for this test only.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      render(<Harness onReady={() => {}} />),
    ).toThrow(/useTheme must be used within a ThemeProvider/);
    spy.mockRestore();
  });
});
