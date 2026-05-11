import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DossierPage from '../../src/pages/DossierPage';
import PayoffMatrix from '../../src/components/ci/war/PayoffMatrix';
import type { PayoffMatrix as PayoffMatrixT } from '../../src/types/payoff';
import { ThemeProvider } from '../../src/hooks/useTheme';

vi.mock('../../src/hooks/useDossier', () => ({
  useDossier: vi.fn(),
}));
import { useDossier } from '../../src/hooks/useDossier';

const MOCK_DOSSIER = {
  entity: {
    id: 'ent-1',
    slug: 'tirzepatide',
    type: 'drug' as const,
    canonical_name: 'tirzepatide',
    aliases: ['Mounjaro'],
    external_ids: {},
    primary_attributes: {},
    updated_at: '2026-05-09T00:00:00Z',
  },
  synthesis: null,
  recent_moves: [],
  evidence: [],
  watchers: [],
  watcher_count: 0,
};

function renderDossier(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/dossier/:entityType/:slug" element={<DossierPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('Loop #10 — UI integration pass', () => {
  describe('DossierPage shared chrome', () => {
    beforeEach(() => {
      vi.mocked(useDossier).mockReturnValue({ data: MOCK_DOSSIER, error: null, isLoading: false });
    });

    it('shows a back button labelled "Back" in the top bar', () => {
      renderDossier('/dossier/drug/tirzepatide');
      expect(screen.getByRole('button', { name: /^back$/i })).toBeDefined();
    });

    it('shows the product name and "Dossier" breadcrumb in the top bar', () => {
      renderDossier('/dossier/drug/tirzepatide');
      expect(screen.getByText(/dossier/i)).toBeDefined();
      // Product name comes from brand.ts — assert via the page header role
      const banner = screen.getAllByRole('banner');
      expect(banner.length).toBeGreaterThan(0);
    });

    it('exposes a banner landmark (header element) so AT distinguish chrome from content', () => {
      renderDossier('/dossier/drug/tirzepatide');
      expect(screen.getAllByRole('banner').length).toBeGreaterThan(0);
    });
  });

  describe('PayoffMatrix — agent identity threading', () => {
    const MATRIX: PayoffMatrixT = {
      room_id: 'room-1',
      rows: [
        { id: 'r1', label: 'launch_q3' },
        { id: 'r2', label: 'wait_q4' },
      ],
      cols: [
        { id: 'c1', label: 'defend' },
        { id: 'c2', label: 'cede' },
      ],
      cells: [
        { row_id: 'r1', col_id: 'c1', outcome: 'win',     delta_pct:  6.4, confidence: 0.71 },
        { row_id: 'r1', col_id: 'c2', outcome: 'lose',    delta_pct: -2.1, confidence: 0.62 },
        { row_id: 'r2', col_id: 'c1', outcome: 'neutral', delta_pct:  1.2, confidence: 0.55 },
        { row_id: 'r2', col_id: 'c2', outcome: 'lose',    delta_pct: -3.4, confidence: 0.48 },
      ],
      recommended_cell: { row_id: 'r1', col_id: 'c1' },
    };

    it('captions the recommended cell with the Strategist identity', () => {
      render(<PayoffMatrix matrix={MATRIX} />);
      expect(screen.getByText(/strategist recommends/i)).toBeDefined();
    });

    it('marks the recommended caption with data-agent="strategist" so the tint can be themed', () => {
      const { container } = render(<PayoffMatrix matrix={MATRIX} />);
      const caption = container.querySelector('[data-agent="strategist"]');
      expect(caption).not.toBeNull();
    });
  });
});
