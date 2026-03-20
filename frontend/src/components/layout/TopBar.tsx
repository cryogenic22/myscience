import { ArrowLeft, Database, MessageSquare, Moon, Network, Search, Sun, Sparkles } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';

interface TopBarProps {
  onBack: () => void;
  onSearch?: () => void;
  activeTab: 'chat' | 'graph' | 'catalog';
  onTabChange: (tab: 'chat' | 'graph' | 'catalog') => void;
  breadcrumb?: string;
}

const TABS: Array<{ key: 'chat' | 'graph' | 'catalog'; label: string; icon: typeof MessageSquare }> = [
  { key: 'chat', label: 'Intelligence', icon: Sparkles },
  { key: 'graph', label: 'Graph', icon: Network },
  { key: 'catalog', label: 'Data', icon: Database },
];

export default function TopBar({ onBack, onSearch, activeTab, onTabChange, breadcrumb }: TopBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-30 shrink-0 bg-white/70 backdrop-blur-2xl dark:bg-slate-900/70">
      <div className="flex h-14 items-center justify-between px-4">
        {/* Left: back + brand + tabs */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="group flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
            title="Back to Home"
            aria-label="Back to Home"
          >
            <ArrowLeft size={15} className="transition-transform group-hover:-translate-x-0.5" />
          </button>

          <div className="h-5 w-px bg-slate-200/80 dark:bg-slate-700" />

          <nav className="flex items-center gap-0.5 rounded-full bg-slate-100/80 p-0.5 dark:bg-slate-800/80">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => onTabChange(tab.key)}
                  className={`relative inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[12px] font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                  aria-label={tab.label}
                >
                  <Icon size={13} />
                  <span className="hidden sm:inline">{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Center: breadcrumb */}
        {breadcrumb && (
          <div className="absolute left-1/2 -translate-x-1/2 truncate text-[11px] text-slate-400 dark:text-slate-500 max-w-[30vw]">
            {breadcrumb}
          </div>
        )}

        {/* Right: search + theme */}
        <div className="flex items-center gap-2">
          {onSearch && (
            <button
              type="button"
              onClick={onSearch}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1.5 text-[11px] text-slate-500 transition-all hover:border-slate-300 hover:shadow-sm dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-400"
              title="Search (Cmd+K)"
              aria-label="Search"
            >
              <Search size={12} />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden rounded border border-slate-200/80 bg-slate-50 px-1 py-0.5 text-[9px] font-medium text-slate-400 sm:inline dark:border-slate-700 dark:bg-slate-800">
                {navigator.platform.includes('Mac') ? '\u2318' : 'Ctrl'}K
              </kbd>
            </button>
          )}

          <button
            type="button"
            onClick={toggleTheme}
            className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        </div>
      </div>
    </header>
  );
}
