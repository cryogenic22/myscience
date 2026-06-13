import { Activity, ArrowLeft, Bell, Database, Layers, Moon, Network, Search, Sparkles, Sun } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { PRODUCT_NAME } from '../../brand';
import { FeedBadge } from '../intelligence/FeedBadge';

export type TopBarTab = 'chat' | 'graph' | 'catalog' | 'search' | 'feed';

interface TopBarProps {
  onBack: () => void;
  onSearch?: () => void;
  /** Jump to the CI cockpit (/ci) — the engagement war-gaming walkthrough. */
  onCI?: () => void;
  /** Jump to the DataHub Catalog (/hub/catalog) — every connected source at a glance. */
  onDataHub?: () => void;
  activeTab: TopBarTab;
  onTabChange: (tab: TopBarTab) => void;
  breadcrumb?: string;
}

const TABS = [
  { key: 'chat' as const, label: 'Intelligence', icon: Sparkles },
  { key: 'feed' as const, label: 'Feed', icon: Bell },
  { key: 'search' as const, label: 'Search', icon: Search },
  { key: 'graph' as const, label: 'Graph', icon: Network },
  { key: 'catalog' as const, label: 'Entity Library', icon: Database },
];

export default function TopBar({ onBack, onSearch, onCI, onDataHub, activeTab, onTabChange, breadcrumb }: TopBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header
      className="topbar sticky top-0 z-30 shrink-0"
      style={{ height: '52px' }}
    >
      <div className="flex h-full items-center gap-4" style={{ padding: '0 20px' }}>
        {/* Back */}
        <button
          type="button"
          onClick={onBack}
          className="btn-icon shrink-0"
          title="Back"
          aria-label="Back"
        >
          <ArrowLeft size={15} />
        </button>

        {/* Brand */}
        <span
          className="font-display mz-text-md font-light shrink-0"
          style={{ color: 'var(--color-ink-3)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>

        <div
          className="h-4 w-px shrink-0"
          style={{ background: 'var(--color-line)' }}
        />

        {/* Tabs — segmented control */}
        <nav
          className="flex items-center rounded-[10px] gap-0.5"
          style={{ padding: '4px', background: 'var(--color-surface-2)' }}
        >
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onTabChange(key)}
              className="nav-tab"
              data-active={activeTab === key}
              style={{
                background: activeTab === key ? 'var(--color-surface)' : 'transparent',
                color: activeTab === key ? 'var(--color-ink)' : 'var(--color-ink-3)',
                boxShadow: activeTab === key ? 'var(--shadow-xs)' : 'none',
              }}
            >
              <Icon size={13} />
              <span className="hidden sm:inline">{label}</span>
              {key === 'feed' && <FeedBadge />}
            </button>
          ))}
        </nav>

        {/* Breadcrumb */}
        {breadcrumb && (
          <div
            className="hidden lg:block truncate mz-text-sm flex-1 text-center"
            style={{ color: 'var(--color-ink-4)' }}
          >
            {breadcrumb}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {onDataHub && (
            <button
              type="button"
              onClick={onDataHub}
              data-testid="topbar-datahub"
              className="btn btn-ghost btn-sm hidden sm:flex items-center gap-2"
              style={{ borderRadius: '8px' }}
              title="Open DataHub — every connected source, dataset & entity at a glance"
            >
              <Layers size={13} />
              <span style={{ color: 'var(--color-ink-3)' }}>DataHub</span>
            </button>
          )}
          {onCI && (
            <button
              type="button"
              onClick={onCI}
              data-testid="topbar-ci"
              className="btn btn-ghost btn-sm hidden sm:flex items-center gap-2"
              style={{ borderRadius: '8px' }}
              title="Open the CI cockpit — engagements & war-gaming"
            >
              <Activity size={13} />
              <span style={{ color: 'var(--color-ink-3)' }}>CI Cockpit</span>
            </button>
          )}
          {onSearch && (
            <button
              type="button"
              onClick={onSearch}
              className="btn btn-ghost btn-sm hidden sm:flex items-center gap-2"
              style={{ borderRadius: '8px' }}
            >
              <Search size={13} />
              <span style={{ color: 'var(--color-ink-3)' }}>Search</span>
              <kbd
                className="rounded"
                style={{
                  padding: '2px 6px',
                  fontSize: '10px',
                  background: 'var(--color-surface-2)',
                  color: 'var(--color-ink-4)',
                  border: '1px solid var(--color-line)',
                }}
              >
                ⌘K
              </kbd>
            </button>
          )}

          <button
            type="button"
            onClick={toggleTheme}
            className="btn-icon"
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          {/* Live dot */}
          <div
            className="flex h-8 w-8 items-center justify-center rounded-[8px]"
            style={{ background: 'var(--color-surface-2)' }}
          >
            <span
              className="h-2 w-2 rounded-full pulse-live"
              style={{ background: '#22C55E' }}
            />
          </div>
        </div>
      </div>
    </header>
  );
}
