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
    <aside className="w-16 md:w-[76px] shrink-0 border-r border-slate-200/75 dark:border-slate-700/50 bg-white/88 dark:bg-slate-900/90 backdrop-blur-md transition-all">
      <div className="flex h-full flex-col items-center py-3">
        {/* Back button */}
        <button
          type="button"
          onClick={onBack}
          className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          title="Back to Home"
          aria-label="Back to Home"
        >
          <ArrowLeft size={16} />
        </button>

        {/* Logo */}
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
          <Zap size={15} strokeWidth={2.4} />
        </div>

        {/* Navigation groups */}
        <nav className="flex flex-col items-center gap-3">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="flex flex-col items-center gap-1">
              <span className="hidden md:block text-[8px] font-semibold uppercase tracking-widest text-slate-300 dark:text-slate-600 mb-0.5">
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
                    className={`group relative flex flex-col items-center justify-center w-12 md:w-14 rounded-xl transition-all ${
                      isActive
                        ? 'bg-brand text-white shadow-sm border-l-[3px] border-brand-dark'
                        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-300'
                    }`}
                    style={{ minHeight: 44 }}
                    title={item.label}
                    aria-label={item.label}
                  >
                    <Icon size={16} />
                    <span className={`hidden md:block text-[9px] mt-0.5 leading-tight ${
                      isActive ? 'font-semibold text-white' : 'text-slate-400 group-hover:text-slate-600'
                    }`}>
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
            className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-300"
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200/70 dark:border-slate-700/50 bg-white/86 dark:bg-slate-800/80 shadow-sm">
            <span className="h-2 w-2 rounded-full bg-emerald-500 pulse-live" />
          </div>
        </div>
      </div>
    </aside>
  );
}
