import { ArrowLeft, Database, MessageSquare, Moon, Network, Search, Sun, Zap } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';

type WorkspaceView = 'chat' | 'graph' | 'search' | 'catalog';

interface Props {
  active: WorkspaceView;
  onSelect: (view: WorkspaceView) => void;
  onBack: () => void;
}

const NAV_GROUPS: Array<{
  label: string;
  items: Array<{ key: WorkspaceView; label: string; icon: typeof MessageSquare }>;
}> = [
  {
    label: 'Intelligence',
    items: [
      { key: 'chat', label: 'Chat', icon: MessageSquare },
      { key: 'search', label: 'Search', icon: Search },
    ],
  },
  {
    label: 'Explore',
    items: [
      { key: 'graph', label: 'Graph', icon: Network },
      { key: 'catalog', label: 'Data', icon: Database },
    ],
  },
];

export default function WorkspaceRail({ active, onSelect, onBack }: Props) {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside
      className="w-16 md:w-[76px] shrink-0 backdrop-blur-md transition-all"
      style={{
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-line)',
      }}
    >
      <div className="flex h-full flex-col items-center py-3">
        {/* Back button */}
        <button
          type="button"
          onClick={onBack}
          className="btn-icon mb-3"
          style={{ width: 36, height: 36, borderRadius: 12, background: 'transparent', color: 'var(--color-ink-4)' }}
          title="Back to Home"
          aria-label="Back to Home"
        >
          <ArrowLeft size={16} />
        </button>

        {/* Logo */}
        <div
          className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl text-white"
          style={{ background: 'var(--color-accent)', boxShadow: 'var(--shadow-xs)' }}
        >
          <Zap size={15} strokeWidth={2.4} />
        </div>

        {/* Navigation groups */}
        <nav className="flex flex-col items-center gap-3">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="flex flex-col items-center gap-1">
              <span
                className="hidden md:block text-[8px] font-semibold uppercase tracking-widest mb-0.5"
                style={{ color: 'var(--color-ink-4)' }}
              >
                {group.label}
              </span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = active === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onSelect(item.key)}
                    className="group relative flex flex-col items-center justify-center w-12 md:w-14 rounded-xl transition-all"
                    style={{
                      minHeight: 44,
                      background: isActive ? 'var(--color-accent)' : 'transparent',
                      color: isActive ? '#fff' : 'var(--color-ink-3)',
                      boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                      borderLeft: isActive ? '3px solid var(--color-accent-dark)' : '3px solid transparent',
                    }}
                    title={item.label}
                    aria-label={item.label}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'var(--color-surface-2)';
                        e.currentTarget.style.color = 'var(--color-ink)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.color = 'var(--color-ink-3)';
                      }
                    }}
                  >
                    <Icon size={16} />
                    <span
                      className="hidden md:block text-[9px] mt-0.5 leading-tight"
                      style={{
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? '#fff' : 'var(--color-ink-4)',
                      }}
                    >
                      {item.label}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Bottom controls */}
        <div className="mt-auto flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            className="flex h-9 w-9 items-center justify-center rounded-xl transition-colors"
            style={{ color: 'var(--color-ink-4)', background: 'transparent' }}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--color-surface-2)';
              e.currentTarget.style.color = 'var(--color-ink-2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--color-ink-4)';
            }}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <div
            className="flex h-9 w-9 items-center justify-center rounded-xl"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            <span className="h-2 w-2 rounded-full bg-emerald-500 pulse-live" />
          </div>
        </div>
      </div>
    </aside>
  );
}
