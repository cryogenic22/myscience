/**
 * Loop #11 — Design system regression guards.
 *
 * Each test pins down one of the six root causes diagnosed in Loop #11.
 * If a future change reintroduces a bug, the test fails loudly.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DossierPage from '../../src/pages/DossierPage';
import PayoffMatrix from '../../src/components/ci/war/PayoffMatrix';
import { ThemeProvider } from '../../src/hooks/useTheme';
import type { Dossier } from '../../src/types/dossier';
import type { PayoffMatrix as PayoffMatrixT } from '../../src/types/payoff';

vi.mock('../../src/hooks/useDossier', () => ({
  useDossier: vi.fn(),
}));
import { useDossier } from '../../src/hooks/useDossier';

const MOCK_DOSSIER: Dossier = {
  entity: {
    id: 'x', slug: 'tirzepatide', type: 'drug',
    canonical_name: 'tirzepatide',
    aliases: [], external_ids: {}, primary_attributes: {},
    updated_at: '2026-05-09T00:00:00Z',
  },
  synthesis: null,
  recent_moves: [],
  evidence: [],
  watchers: [],
  watcher_count: 0,
};

const MATRIX: PayoffMatrixT = {
  room_id: 'r',
  rows: [{ id: 'r1', label: 'launch' }, { id: 'r2', label: 'wait' }],
  cols: [{ id: 'c1', label: 'defend' }, { id: 'c2', label: 'cede' }],
  cells: [
    { row_id: 'r1', col_id: 'c1', outcome: 'win',     delta_pct:  6.4, confidence: 0.71 },
    { row_id: 'r1', col_id: 'c2', outcome: 'lose',    delta_pct: -2.1, confidence: 0.62 },
    { row_id: 'r2', col_id: 'c1', outcome: 'neutral', delta_pct:  1.2, confidence: 0.55 },
    { row_id: 'r2', col_id: 'c2', outcome: 'lose',    delta_pct: -3.4, confidence: 0.48 },
  ],
  recommended_cell: { row_id: 'r1', col_id: 'c1' },
};

function renderDossier() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/dossier/drug/tirzepatide']}>
        <Routes>
          <Route path="/dossier/:entityType/:slug" element={<DossierPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('Loop #11 — design system regression guards', () => {
  describe('Fix A: display headings use the canonical display font, not Tailwind font-serif (Georgia)', () => {
    it('DossierPage entity-name H1 does not use the bare Tailwind `font-serif` class', () => {
      vi.mocked(useDossier).mockReturnValue({ data: MOCK_DOSSIER, error: null, isLoading: false });
      renderDossier();
      const heading = screen.getByRole('heading', { level: 1, name: /tirzepatide/i });
      // `font-serif` resolves to Tailwind's Georgia stack. We want `font-display`
      // which resolves to our --font-display CSS variable (Fraunces).
      expect(heading.classList.contains('font-serif')).toBe(false);
      expect(heading.classList.contains('font-display')).toBe(true);
    });

    it('PayoffMatrix payoff-matrix heading does not use bare `font-serif`', () => {
      const { container } = render(<PayoffMatrix matrix={MATRIX} />);
      const heading = container.querySelector('h3');
      expect(heading).not.toBeNull();
      expect(heading?.classList.contains('font-serif')).toBe(false);
      expect(heading?.classList.contains('font-display')).toBe(true);
    });
  });

  describe('Fix B: borderless surfaces — do not draw 1px solid boxes around panels', () => {
    it('PayoffMatrix root section does not ship a 1px solid border', () => {
      const { container } = render(<PayoffMatrix matrix={MATRIX} />);
      const root = container.querySelector('section');
      expect(root).not.toBeNull();
      const inline = root!.getAttribute('style') ?? '';
      // Allow borderless OR an explicit "none". Disallow "1px solid".
      expect(inline).not.toMatch(/border:\s*1px\s*solid/i);
    });
  });

  describe('Fix D: type scale — display heading sizes come from the scale, not from arbitrary text-[Npx]', () => {
    it('DossierPage entity-name H1 uses the new display type-scale class', () => {
      vi.mocked(useDossier).mockReturnValue({ data: MOCK_DOSSIER, error: null, isLoading: false });
      renderDossier();
      const heading = screen.getByRole('heading', { level: 1, name: /tirzepatide/i });
      // `mz-text-display` is the new type-scale utility for hero headings.
      // If someone replaces it with another arbitrary text-[Npx] this fails.
      expect(heading.classList.contains('mz-text-display')).toBe(true);
    });
  });
});
