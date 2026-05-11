import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import BriefComposerPage from '../../src/pages/BriefComposerPage';
import { ThemeProvider } from '../../src/hooks/useTheme';

function renderAt(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/briefs/new" element={<BriefComposerPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('BriefComposerPage (PB-401 scaffold)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the app chrome with a "Brief" breadcrumb', () => {
    renderAt('/briefs/new');
    expect(screen.getByRole('button', { name: /^back$/i })).toBeDefined();
    expect(screen.getByText('Brief')).toBeDefined();
  });

  it('mounts a TipTap editor surface with a placeholder', () => {
    renderAt('/briefs/new');
    const editor = document.querySelector('[contenteditable="true"]');
    expect(editor).not.toBeNull();
  });

  it('shows the mock-data banner about BE-19 not being merged', () => {
    renderAt('/briefs/new');
    expect(screen.getByText(/placeholder data/i)).toBeDefined();
    expect(screen.getByText(/BE-19/i)).toBeDefined();
  });

  it('exposes a Save button + an autosave status indicator (Saved / Saving…)', () => {
    renderAt('/briefs/new');
    expect(screen.getByRole('button', { name: /save/i })).toBeDefined();
    expect(screen.getByText(/saved/i)).toBeDefined();
  });

  it('renders a {{cite:doc_id}} fixture as a chip in the rendered HTML', () => {
    renderAt('/briefs/new?fixture=cite');
    // The placeholder fixture content includes a cite token rendered
    // through the custom mark.
    const chip = document.querySelector('[data-citation="doc-1"]');
    expect(chip).not.toBeNull();
  });
});
