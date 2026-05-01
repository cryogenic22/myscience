import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import DigestTab from '../components/ci/DigestTab';
import SignalsTab from '../components/ci/SignalsTab';
import WatchlistTab from '../components/ci/WatchlistTab';

type TabKey = 'digest' | 'signals' | 'watchlist' | 'reviewer';

const ALL_TABS: Array<{ key: TabKey; label: string; enterprise?: boolean }> = [
  { key: 'digest',    label: 'Digest' },
  { key: 'signals',   label: 'Signals' },
  { key: 'watchlist', label: 'Watchlist' },
  { key: 'reviewer',  label: 'Reviewer', enterprise: true },
];

function getRole(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('mz_auth_role');
}

export default function CIPage() {
  const navigate = useNavigate();
  const role = getRole();
  const isEnterprise = role === 'enterprise';
  const tabs = ALL_TABS.filter((t) => !t.enterprise || isEnterprise);
  const [tab, setTab] = useState<TabKey>('digest');

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--color-surface)' }}>
      {/* Header */}
      <header
        className="shrink-0 flex items-center gap-4"
        style={{
          height: '52px',
          padding: '0 20px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/')}
          className="btn-icon"
          aria-label="Back"
          title="Back"
        >
          <ArrowLeft size={15} />
        </button>
        <span
          className="font-display text-[15px] font-light"
          style={{ color: 'var(--color-ink-3)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>
        <div className="h-4 w-px" style={{ background: 'var(--color-line)' }} />
        <span className="font-display text-[15px]" style={{ color: 'var(--color-ink)' }}>
          Competitive Intelligence
        </span>

        {/* Tab nav */}
        <nav
          className="ml-6 flex items-center gap-0.5 rounded-[10px]"
          style={{ padding: '4px', background: 'var(--color-surface-2)' }}
        >
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className="text-[12px] font-medium"
              style={{
                padding: '5px 12px',
                borderRadius: '6px',
                background: tab === t.key ? 'var(--color-surface)' : 'transparent',
                color: tab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
                boxShadow: tab === t.key ? 'var(--shadow-xs)' : 'none',
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <a
            href="/connectors"
            className="text-[11px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            Connectors →
          </a>
          {role && (
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-3)',
                letterSpacing: '0.06em',
              }}
            >
              {role}
            </span>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === 'digest' && <DigestTab />}
        {tab === 'signals' && <SignalsTab />}
        {tab === 'watchlist' && <WatchlistTab />}
        {tab === 'reviewer' && isEnterprise && (
          <SignalsTab reviewerMode initialStatus="candidate" />
        )}
      </div>
    </div>
  );
}
