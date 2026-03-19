import { ArrowLeft, Database, MessageSquare, Moon, Network, Search, Sun, Zap } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';

interface TopBarProps {
  onBack: () => void;
  onSearch?: () => void;
  activeTab: 'chat' | 'graph' | 'catalog';
  onTabChange: (tab: 'chat' | 'graph' | 'catalog') => void;
  breadcrumb?: string;
}

const TABS: Array<{ key: 'chat' | 'graph' | 'catalog'; label: string; icon: typeof MessageSquare }> = [
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'graph', label: 'Graph', icon: Network },
  { key: 'catalog', label: 'Data', icon: Database },
];

export default function TopBar({ onBack, onSearch, activeTab, onTabChange, breadcrumb }: TopBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-30 flex h-[52px] shrink-0 items-center border-b border-slate-200/75 bg-white/80 backdrop-blur-xl">
      {/* Left: logo + back + tabs */}
      <div className="flex items-center gap-2 pl-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          title="Back to Home"
          aria-label="Back to Home"
        >
          <ArrowLeft size={16} />
        </button>

        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white">
          <Zap size={14} strokeWidth={2.4} />
        </div>

        <nav className="ml-2 flex items-center gap-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => onTabChange(tab.key)}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  isActive
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                }`}
                aria-label={tab.label}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Center: breadcrumb */}
      <div className="flex-1 px-4">
        {breadcrumb && (
          <div className="truncate text-center text-[11px] font-medium text-slate-400">
            {breadcrumb}
          </div>
        )}
      </div>

      {/* Right: search + theme */}
      <div className="flex items-center gap-1.5 pr-3">
        {onSearch && (
          <button
            type="button"
            onClick={onSearch}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700"
            title="Search (Cmd+K)"
            aria-label="Search"
          >
            <Search size={13} />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden rounded border border-slate-200 bg-slate-50 px-1 py-0.5 text-[9px] font-medium text-slate-400 sm:inline">
              {navigator.platform.includes('Mac') ? '\u2318' : 'Ctrl'}K
            </kbd>
          </button>
        )}

        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>
    </header>
  );
}
