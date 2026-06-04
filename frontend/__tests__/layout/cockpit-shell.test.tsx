/**
 * D1 — Cockpit shell primitive tests.
 *
 * Pin the structural contract:
 *   - No hardcoded hex codes in primitive inline styles
 *   - No `border-r/border-b/border-t` for region separation
 *   - No hardcoded data-theme
 *   - Primitives honor their slot contract (children render in expected positions)
 *
 * Includes the SPEC_D1 acceptance test as a single function.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { CockpitShell } from '../../src/components/layout/CockpitShell';
import { NavRail } from '../../src/components/layout/NavRail';
import { NavRailItem } from '../../src/components/layout/NavRailItem';
import { ContentRegion } from '../../src/components/layout/ContentRegion';
import { CockpitMobileNav } from '../../src/components/layout/CockpitMobileNav';

const HEX_PATTERN = /#[0-9a-fA-F]{3,8}\b/;

function NoopIcon({ size }: { size?: number }) {
  return <span data-testid="icon" data-size={size}>icon</span>;
}

// ──────────────────────────────────────────────────────
// CockpitShell — root container
// ──────────────────────────────────────────────────────

describe('CockpitShell', () => {
  it('renders nav slot + main content', () => {
    render(
      <CockpitShell nav={<div data-testid="nav-content">N</div>}>
        <div data-testid="main-content">M</div>
      </CockpitShell>,
    );
    expect(screen.getByTestId('nav-content')).toBeInTheDocument();
    expect(screen.getByTestId('main-content')).toBeInTheDocument();
  });

  it('does NOT hardcode data-theme (lets user theme propagate)', () => {
    render(<CockpitShell nav={<div>n</div>}>m</CockpitShell>);
    const shell = screen.getByTestId('cockpit-shell');
    expect(shell).not.toHaveAttribute('data-theme');
  });

  it('inline styles use CSS variables, not hex codes', () => {
    render(<CockpitShell nav={<div>n</div>}>m</CockpitShell>);
    const shell = screen.getByTestId('cockpit-shell');
    const styleAttr = shell.getAttribute('style') || '';
    expect(styleAttr).not.toMatch(HEX_PATTERN);
    // Positive assertion: it uses a token.
    expect(styleAttr).toMatch(/var\(--color-bg\)/);
  });

  it('renders optional mobileNav slot when provided', () => {
    render(
      <CockpitShell
        nav={<div>n</div>}
        mobileNav={<div data-testid="mob-nav">mobile</div>}
      >
        m
      </CockpitShell>,
    );
    expect(screen.getByTestId('mob-nav')).toBeInTheDocument();
  });
});

// ──────────────────────────────────────────────────────
// NavRail — left sidebar
// ──────────────────────────────────────────────────────

describe('NavRail', () => {
  it('renders header, children, and footer slots in order', () => {
    render(
      <NavRail header={<div data-testid="h">H</div>} footer={<div data-testid="f">F</div>}>
        <div data-testid="b">B</div>
      </NavRail>,
    );
    const rail = screen.getByTestId('nav-rail');
    const h = screen.getByTestId('h');
    const b = screen.getByTestId('b');
    const f = screen.getByTestId('f');
    // Order: header → body → footer
    expect(rail.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_CONTAINED_BY).toBeTruthy();
    expect(h.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(b.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('uses tone-shifted surface, never border-r for separation', () => {
    render(<NavRail>n</NavRail>);
    const rail = screen.getByTestId('nav-rail');
    // Class list must not include any border-r/border-l/border-t/border-b utility.
    const cls = rail.className;
    expect(cls).not.toMatch(/\bborder-(r|l|t|b)\b/);
    // Inline style uses surface-2 token.
    expect(rail.getAttribute('style') || '').toMatch(/var\(--color-surface-2\)/);
  });

  it('does not include any hardcoded hex codes', () => {
    render(<NavRail header={<div>h</div>} footer={<div>f</div>}>n</NavRail>);
    const rail = screen.getByTestId('nav-rail');
    expect(rail.getAttribute('style') || '').not.toMatch(HEX_PATTERN);
  });
});

// ──────────────────────────────────────────────────────
// NavRailItem — sidebar nav button
// ──────────────────────────────────────────────────────

describe('NavRailItem', () => {
  it('renders label + icon and fires onClick', () => {
    const onClick = vi.fn();
    render(<NavRailItem label="Sensing" icon={NoopIcon} onClick={onClick} />);
    const btn = screen.getByRole('button', { name: /sensing/i });
    btn.click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('inactive item uses ink-3 color, active uses ink', () => {
    const { rerender } = render(
      <NavRailItem label="A" icon={NoopIcon} onClick={() => {}} />,
    );
    const inactive = screen.getByRole('button', { name: /a/i });
    expect(inactive.getAttribute('style') || '').toMatch(/var\(--color-ink-3\)/);

    rerender(<NavRailItem label="A" icon={NoopIcon} active onClick={() => {}} />);
    const active = screen.getByRole('button', { name: /a/i });
    expect(active.getAttribute('style') || '').toMatch(/var\(--color-ink\)/);
  });

  it('active state uses surface-3 background, not a border/ring', () => {
    render(<NavRailItem label="X" icon={NoopIcon} active onClick={() => {}} />);
    const btn = screen.getByRole('button', { name: /x/i });
    expect(btn.getAttribute('style') || '').toMatch(/var\(--color-surface-3\)/);
    expect(btn.className).not.toMatch(/\bring-/);
    expect(btn.className).not.toMatch(/\bborder-/);
  });

  it('no hardcoded hex in either state', () => {
    const { rerender } = render(<NavRailItem label="X" icon={NoopIcon} onClick={() => {}} />);
    expect(screen.getByRole('button').getAttribute('style') || '').not.toMatch(HEX_PATTERN);
    rerender(<NavRailItem label="X" icon={NoopIcon} active onClick={() => {}} />);
    expect(screen.getByRole('button').getAttribute('style') || '').not.toMatch(HEX_PATTERN);
  });
});

// ──────────────────────────────────────────────────────
// ContentRegion — main scrollable area
// ──────────────────────────────────────────────────────

describe('ContentRegion', () => {
  it('renders children', () => {
    render(<ContentRegion><div data-testid="kid">content</div></ContentRegion>);
    expect(screen.getByTestId('kid')).toBeInTheDocument();
  });

  it('default maxWidth is the generous xl cap; honors override', () => {
    // Layout is inline (Railway-safe) — assert the computed style, not a class.
    const { rerender } = render(<ContentRegion>x</ContentRegion>);
    expect(screen.getByTestId('content-region').style.maxWidth).toBe('1440px');
    expect(screen.getByTestId('content-region').style.marginInline).toBe('auto');
    rerender(<ContentRegion maxWidth="2xl">x</ContentRegion>);
    expect(screen.getByTestId('content-region').style.maxWidth).toBe('1760px');
    rerender(<ContentRegion maxWidth="none">x</ContentRegion>);
    expect(screen.getByTestId('content-region').style.maxWidth).toBe('100%');
  });

  it('no hardcoded hex codes', () => {
    render(<ContentRegion>x</ContentRegion>);
    const node = screen.getByTestId('content-region').parentElement; // outer scroll wrapper
    expect((node?.getAttribute('style') || '')).not.toMatch(HEX_PATTERN);
  });
});

// ──────────────────────────────────────────────────────
// CockpitMobileNav — bottom nav
// ──────────────────────────────────────────────────────

describe('CockpitMobileNav', () => {
  const items = [
    { key: 'a' as const, label: 'A', icon: NoopIcon },
    { key: 'b' as const, label: 'B', icon: NoopIcon },
  ];

  it('renders all items + highlights active + fires onChange', () => {
    const onChange = vi.fn();
    render(<CockpitMobileNav items={items} active="a" onChange={onChange} />);
    const a = screen.getByRole('button', { name: /a/i });
    const b = screen.getByRole('button', { name: /b/i });
    expect(a.getAttribute('style') || '').toMatch(/var\(--color-accent\)/);
    expect(b.getAttribute('style') || '').toMatch(/var\(--color-ink-3\)/);
    b.click();
    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('no hardcoded hex codes', () => {
    render(<CockpitMobileNav items={items} active="a" onChange={() => {}} />);
    const nav = screen.getByTestId('cockpit-mobile-nav');
    expect(nav.getAttribute('style') || '').not.toMatch(HEX_PATTERN);
  });
});

// ──────────────────────────────────────────────────────
// SPEC_D1 acceptance test
// ──────────────────────────────────────────────────────

describe('acceptance — D1 contract', () => {
  it('reproduces the SPEC_D1 acceptance test', () => {
    // 1. CockpitShell does NOT hardcode data-theme.
    render(<CockpitShell nav={<NavRail>n</NavRail>}>main</CockpitShell>);
    const shell = screen.getByTestId('cockpit-shell');
    expect(shell).not.toHaveAttribute('data-theme');

    // 2. Inline styles use CSS variables, not hex literals.
    expect(shell.getAttribute('style') || '').not.toMatch(HEX_PATTERN);

    // 3. NavRail uses tone-shift surface, never `border-r`.
    const rail = screen.getByTestId('nav-rail');
    expect(rail.className).not.toMatch(/\bborder-r\b/);

    // 4. NavRailItem active state uses surface elevation, not a ring/border.
    render(<NavRailItem label="x" icon={NoopIcon} active onClick={() => {}} />);
    const item = screen.getByRole('button', { name: /x/i });
    expect(item.getAttribute('style') || '').not.toMatch(HEX_PATTERN);
    expect(item.className).not.toMatch(/\bring-/);
    expect(item.className).not.toMatch(/\bborder-/);
  });
});
