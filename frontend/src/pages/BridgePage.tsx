import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity, Star, Layers, Swords, BookOpen, Rewind,
  Telescope, Bot,
} from 'lucide-react';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import MomentView from '../components/helix/MomentView';
import {
  signalsApi, bridgeApi,
  type Signal,
} from '../api';
import {
  IMPACT_CATEGORIES, tierFor, categoryFor,
  type ImpactCategoryId, type Moment, type Play,
} from '../types/helix';

/**
 * Loop #17 — Helix Bridge MVP.
 *
 * Top-level `/bridge` surface. Sidebar shell + hero + 3-zone layout
 * (Pulse signals · Digital Twin graph · AI Moments). Pulse wires to
 * the real `/signals` API; Moments wires to the new `POST
 * /bridge/moments` LLM-synthesised endpoint; Decision Ledger pin
 * opens a slide-over of real briefs.
 *
 * Spec: `specs/SPEC_LOOP_17_helix_bridge.md`
 * Reference prototype: `specs/helix_proto.tsx`
 */

type BridgeMode = 'live' | 'today' | 'week';

export default function BridgePage() {
  const [mode, setMode] = useState<BridgeMode>('live');
  const [signals, setSignals] = useState<Signal[]>([]);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<ImpactCategoryId | 'all'>('all');
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [activeMoment, setActiveMoment] = useState<Moment | null>(null);

  useEffect(() => {
    void signalsApi.list({ limit: 30 }).then((r) => setSignals(r.signals)).catch(() => setSignals([]));
  }, []);

  useEffect(() => {
    void bridgeApi
      .moments(3, mode === 'week' ? 7 : mode === 'today' ? 1 : 7)
      .then((r) => setMoments(r.moments))
      .catch(() => setMoments([]));
  }, [mode]);

  const filteredSignals = useMemo(
    () =>
      [...signals]
        .filter((s) =>
          categoryFilter === 'all'
            ? true
            : categoryFor(s.kbq_tags).id === categoryFilter,
        )
        .sort((a, b) => Number(b.impact_score ?? 0) - Number(a.impact_score ?? 0)),
    [signals, categoryFilter],
  );

  const topMoment = moments[0];

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg)' }}>
      <HelixSidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <HelixHeader ledgerOpen={ledgerOpen} setLedgerOpen={setLedgerOpen} />
        <main className="flex-1 overflow-auto" style={{ padding: '20px 24px' }}>
          <BridgeModeToggle mode={mode} setMode={setMode} />
          {topMoment && <HeroStrip moment={topMoment} onOpen={setActiveMoment} />}
          <div
            className="grid"
            style={{
              gridTemplateColumns: 'minmax(320px, 1fr) minmax(380px, 1.4fr) minmax(320px, 1fr)',
              gap: '16px',
              marginTop: '20px',
            }}
          >
            <PulseZone
              signals={filteredSignals}
              categoryFilter={categoryFilter}
              setCategoryFilter={setCategoryFilter}
            />
            <TwinZone hoverNode={hoverNode} setHoverNode={setHoverNode} />
            <MomentsZone moments={moments} onOpen={setActiveMoment} />
          </div>
        </main>
      </div>
      {ledgerOpen && <DecisionLedgerSlideOver close={() => setLedgerOpen(false)} />}
      {activeMoment && (
        <MomentView moment={activeMoment} signals={signals} close={() => setActiveMoment(null)} />
      )}
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────

function HelixSidebar() {
  const primary = [
    { id: 'bridge',    label: 'Bridge',         icon: Activity,  to: '/bridge', active: true },
    { id: 'watchlist', label: 'Watchlist',      icon: Star,      to: '/watchlist' },
    { id: 'kbq',       label: 'KBQ Workspace',  icon: Layers,    to: '/kbq' },
    { id: 'wargame',   label: 'War Game',       icon: Swords,    to: '/wargame' },
    { id: 'knowledge', label: 'Knowledge',      icon: BookOpen,  to: '/knowledge' },
    { id: 'replay',    label: 'Replay',         icon: Rewind,    to: '/replay' },
  ];
  const oversight = [
    { id: 'reviewer', label: 'Reviewer', icon: Telescope, to: '/reviewer' },
    { id: 'agents',   label: 'Agents',    icon: Bot,        to: '/agents' },
  ];
  return (
    <aside
      className="shrink-0 flex flex-col"
      style={{
        width: '224px',
        borderRight: '1px solid var(--color-divider)',
        background: 'var(--color-surface)',
      }}
    >
      <div style={{ padding: '20px 18px', borderBottom: '1px solid var(--color-divider)' }}>
        <div className="flex items-center gap-2.5">
          <svg viewBox="0 0 28 28" style={{ width: 26, height: 26 }}>
            <circle cx="14" cy="14" r="11" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
            <circle cx="14" cy="14" r="6"  fill="none" stroke="rgb(139,92,246)" strokeWidth="1.5" />
            <circle cx="14" cy="14" r="2"  fill="var(--color-accent)" />
          </svg>
          <div>
            <div className="font-display" style={{ fontSize: 'var(--text-lg)', lineHeight: 1, color: 'var(--color-ink)' }}>
              MarketZero
            </div>
            <div
              className="mz-text-xs uppercase"
              style={{ color: 'var(--color-ink-4)', letterSpacing: '0.18em', marginTop: 3 }}
            >
              · Helix
            </div>
          </div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto" style={{ padding: '16px 10px' }}>
        {primary.map((n) => (
          <SidebarLink key={n.id} {...n} />
        ))}
        <div
          className="mz-text-xs uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.15em', padding: '20px 12px 8px' }}
        >
          Oversight
        </div>
        {oversight.map((n) => (
          <SidebarLink key={n.id} {...n} />
        ))}
      </nav>
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--color-divider)' }}>
        <Link
          to="/connectors"
          className="mz-text-xs flex items-center justify-between"
          style={{
            color: 'var(--color-ink-4)',
            letterSpacing: '0.1em',
            textDecoration: 'none',
            padding: '6px 8px',
          }}
        >
          <span>CONNECTORS</span>
          <span>→</span>
        </Link>
      </div>
    </aside>
  );
}

function SidebarLink({
  to, icon: Icon, label, active,
}: { to: string; icon: typeof Activity; label: string; active?: boolean }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 mz-text-sm"
      style={{
        padding: '10px 12px',
        borderRadius: 8,
        marginBottom: 2,
        background: active ? 'var(--color-surface-2)' : 'transparent',
        color: active ? 'var(--color-ink)' : 'var(--color-ink-3)',
        textDecoration: 'none',
        fontWeight: active ? 600 : 400,
        position: 'relative',
      }}
    >
      {active && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute', left: 0, top: 8, bottom: 8, width: 2,
            background: 'var(--color-accent)', borderRadius: 2,
          }}
        />
      )}
      <Icon size={14} style={{ color: active ? 'var(--color-accent)' : 'var(--color-ink-4)' }} />
      <span>{label}</span>
    </Link>
  );
}

// ── Header ─────────────────────────────────────────────────────

function HelixHeader({
  ledgerOpen, setLedgerOpen,
}: { ledgerOpen: boolean; setLedgerOpen: (v: boolean) => void }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);
  return (
    <header
      className="shrink-0 flex items-center gap-4"
      style={{
        height: 52,
        padding: '0 24px',
        borderBottom: '1px solid var(--color-divider)',
        background: 'var(--color-surface)',
      }}
    >
      <div className="ml-auto flex items-center gap-4">
        <span
          className="mz-text-xs flex items-center gap-2"
          style={{ color: 'var(--color-ink-3)' }}
        >
          <span
            style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'rgb(34,197,94)',
            }}
            className="pulse-soft"
          />
          11 agents · live
        </span>
        <button
          type="button"
          onClick={() => setLedgerOpen(!ledgerOpen)}
          className="mz-text-sm flex items-center gap-2"
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: 'var(--color-surface-2)',
            color: 'var(--color-ink)',
            border: 'none',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          <span style={{ color: 'var(--color-accent)' }}>◆</span>
          <span>Decisions</span>
          <span
            className="font-mono mz-text-xs"
            style={{ color: 'var(--color-ink-3)' }}
          >
            · 47
          </span>
        </button>
        <span
          className="font-mono mz-text-xs"
          style={{ color: 'var(--color-ink-3)' }}
        >
          {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}

// ── Bridge mode toggle ─────────────────────────────────────────

function BridgeModeToggle({
  mode, setMode,
}: { mode: BridgeMode; setMode: (m: BridgeMode) => void }) {
  const opts: Array<{ id: BridgeMode; label: string }> = [
    { id: 'live',  label: 'Live' },
    { id: 'today', label: "Today's Digest" },
    { id: 'week',  label: 'This Week' },
  ];
  return (
    <div
      className="flex items-center gap-3"
      style={{ marginBottom: 16 }}
    >
      <div
        className="flex"
        style={{
          padding: 4,
          background: 'var(--color-surface)',
          border: '1px solid var(--color-divider)',
          borderRadius: 10,
          gap: 2,
        }}
      >
        {opts.map((o) => (
          <button
            key={o.id}
            type="button"
            onClick={() => setMode(o.id)}
            className="mz-text-xs"
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: 'none',
              background: mode === o.id ? 'var(--color-surface-2)' : 'transparent',
              color: mode === o.id ? 'var(--color-ink)' : 'var(--color-ink-3)',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontWeight: 500,
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <span
        className="ml-auto mz-text-xs"
        style={{ color: 'var(--color-ink-4)' }}
      >
        {mode === 'live'
          ? 'Continuous monitoring'
          : mode === 'today'
          ? "Top signals & moments for today"
          : 'Week-in-review'}
      </span>
    </div>
  );
}

// ── Hero strip ─────────────────────────────────────────────────

function HeroStrip({ moment, onOpen }: { moment: Moment; onOpen?: (m: Moment) => void }) {
  return (
    <section
      className="flex items-center gap-5"
      style={{
        padding: '18px 24px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-divider)',
        borderRadius: 12,
      }}
    >
      <span
        style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'rgb(245,158,11)',
        }}
        className="pulse-soft"
      />
      <div className="flex-1">
        <div
          className="mz-text-xs uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.15em', marginBottom: 4 }}
        >
          MOST URGENT · NEXT {moment.expires_hours}H
        </div>
        <div
          className="font-display mz-text-xl"
          style={{ color: 'var(--color-ink)' }}
        >
          {moment.title}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onOpen?.(moment)}
        className="mz-text-sm font-display"
        style={{
          padding: '10px 16px',
          borderRadius: 8,
          background: 'var(--color-accent)',
          color: 'white',
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
          fontFamily: 'inherit',
        }}
      >
        Open Moment →
      </button>
      <div style={{ textAlign: 'right' }}>
        <div
          className="mz-text-xs uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.1em' }}
        >
          EV AT STAKE
        </div>
        <div
          className="font-mono"
          style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--color-accent)' }}
        >
          {`$${moment.ev_at_stake_musd}M`}
        </div>
      </div>
    </section>
  );
}

// ── Pulse zone ─────────────────────────────────────────────────

function PulseZone({
  signals, categoryFilter, setCategoryFilter,
}: {
  signals: Signal[];
  categoryFilter: ImpactCategoryId | 'all';
  setCategoryFilter: (v: ImpactCategoryId | 'all') => void;
}) {
  return (
    <section
      aria-label="Pulse"
      className="flex flex-col"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-divider)',
        borderRadius: 12,
        padding: 18,
        maxHeight: 'calc(100vh - 280px)',
        overflow: 'hidden',
      }}
    >
      <header className="flex items-center justify-between" style={{ marginBottom: 12 }}>
        <div>
          <h2 className="font-display mz-text-lg" style={{ color: 'var(--color-ink)' }}>
            Pulse
          </h2>
          <div
            className="mz-text-xs uppercase"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.1em', marginTop: 2 }}
          >
            SENSING FEED · {signals.length} SIGNALS
          </div>
        </div>
        <span className="mz-text-xs flex items-center gap-1" style={{ color: 'var(--color-ink-3)' }}>
          <span
            style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'rgb(34,197,94)',
            }}
            className="pulse-soft"
          />
          live
        </span>
      </header>

      <div
        className="flex gap-1.5 overflow-x-auto"
        style={{ marginBottom: 12, paddingBottom: 4 }}
        role="toolbar"
        aria-label="Category filter"
      >
        <CategoryChip
          label="All"
          color="var(--color-ink-3)"
          active={categoryFilter === 'all'}
          onClick={() => setCategoryFilter('all')}
        />
        {IMPACT_CATEGORIES.map((c) => (
          <CategoryChip
            key={c.id}
            label={c.label}
            color={c.color}
            active={categoryFilter === c.id}
            onClick={() => setCategoryFilter(c.id)}
          />
        ))}
      </div>

      <div className="flex-1 overflow-y-auto flex flex-col gap-1.5">
        {signals.length === 0 ? (
          <p className="mz-text-sm" style={{ color: 'var(--color-ink-4)', padding: '12px 4px' }}>
            No signals yet. The sentinel agents will populate this feed as new evidence arrives.
          </p>
        ) : (
          signals.map((s) => <PulseSignalRow key={s.id} signal={s} />)
        )}
      </div>

      <div
        className="mz-text-xs"
        style={{
          marginTop: 10, paddingTop: 10,
          borderTop: '1px solid var(--color-divider)',
          color: 'var(--color-ink-4)', textAlign: 'center',
        }}
      >
        Browse all signals →
      </div>
    </section>
  );
}

function CategoryChip({
  label, color, active, onClick,
}: { label: string; color: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mz-text-xs"
      style={{
        flexShrink: 0,
        padding: '4px 10px',
        borderRadius: 12,
        border: 'none',
        background: active ? `${color}28` : 'var(--color-surface-2)',
        color: active ? color : 'var(--color-ink-3)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontWeight: 500,
      }}
    >
      {label}
    </button>
  );
}

function PulseSignalRow({ signal }: { signal: Signal }) {
  const cat = categoryFor(signal.kbq_tags);
  const tier = tierFor(signal.impact_score);
  const tierColor =
    tier === 1 ? 'rgb(239,68,68)' :
    tier === 2 ? 'rgb(245,158,11)' :
    'var(--color-ink-4)';
  const materiality = Number(signal.impact_score ?? 0);
  const stroke = (materiality / 10) * 88; // dial circumference

  return (
    <article
      className="mz-elevated flex gap-3"
      style={{
        padding: '10px 12px',
        borderRadius: 8,
        borderLeft: `2px solid ${cat.color}`,
        background: 'var(--color-surface)',
        opacity: tier === 3 ? 0.7 : 1,
      }}
    >
      <div style={{ position: 'relative', width: 36, height: 36, flexShrink: 0 }}>
        <svg viewBox="0 0 36 36" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
          <circle cx={18} cy={18} r={14} fill="none" stroke="var(--color-line)" strokeWidth={2} />
          <circle
            cx={18} cy={18} r={14} fill="none"
            stroke={tierColor} strokeWidth={2.5}
            strokeDasharray={`${stroke} 88`}
            strokeLinecap="round"
          />
        </svg>
        <div
          className="font-mono"
          style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, fontWeight: 700, color: tierColor,
          }}
        >
          {materiality.toFixed(1)}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap" style={{ marginBottom: 4 }}>
          <span
            className="mz-text-xs font-medium"
            style={{
              padding: '1px 6px',
              borderRadius: 4,
              background: `${cat.color}28`,
              color: cat.color,
              fontSize: 9,
            }}
          >
            {cat.label}
          </span>
          <span
            className="mz-text-xs uppercase"
            style={{
              padding: '1px 6px',
              borderRadius: 4,
              background: `${tierColor}28`,
              color: tierColor,
              fontWeight: 700,
              letterSpacing: '0.08em',
              fontSize: 9,
            }}
          >
            Tier {tier}
          </span>
          {signal.primary_entity_name && (
            <span className="mz-text-xs" style={{ color: 'var(--color-ink-4)', fontSize: 9 }}>
              · {signal.primary_entity_name.toUpperCase()}
            </span>
          )}
        </div>
        <div className="mz-text-sm" style={{ color: 'var(--color-ink)', lineHeight: 1.4 }}>
          {signal.headline}
        </div>
      </div>
    </article>
  );
}

// ── Twin zone (seeded SVG until BE-53 ships) ───────────────────

function TwinZone({
  hoverNode, setHoverNode,
}: { hoverNode: string | null; setHoverNode: (id: string | null) => void }) {
  const nodes = useMemo(
    () => [
      { id: 'wegovy',      label: 'Wegovy',      x: 160, y: 160, r: 26, color: '#003b71', core: true, share: 38 },
      { id: 'ozempic',     label: 'Ozempic',     x: 130, y: 250, r: 22, color: '#003b71', share: 24 },
      { id: 'cagrisema',   label: 'CagriSema',   x: 190, y: 330, r: 16, color: '#003b71', phase: 'P3' },
      { id: 'tirzepatide', label: 'Tirzepatide', x: 420, y: 180, r: 28, color: '#d52b1e', share: 32 },
      { id: 'orforglipron',label: 'Orforglipron',x: 470, y: 270, r: 20, color: '#d52b1e', phase: 'P3 oral', pulsing: true },
      { id: 'retatrutide', label: 'Retatrutide', x: 430, y: 340, r: 18, color: '#d52b1e', phase: 'P3' },
      { id: 'maritide',    label: 'MariTide',    x: 470, y: 110, r: 16, color: '#0063c3', phase: 'P3 monthly' },
      { id: 'danuglipron', label: 'Danuglipron', x: 320, y: 90,  r: 14, color: '#0093d0', phase: 'P2 oral' },
      { id: 'patients',    label: 'Patients',    x: 290, y: 220, r: 30, color: 'var(--color-accent)', core: true },
      { id: 'payers',      label: 'Payers',      x: 90,  y: 90,  r: 18, color: 'rgb(139,92,246)' },
      { id: 'cms',         label: 'CMS NCD',     x: 530, y: 50,  r: 14, color: 'rgb(245,158,11)', pulsing: true },
      { id: 'fda',         label: 'FDA',         x: 60,  y: 380, r: 14, color: 'rgb(245,158,11)' },
    ],
    [],
  );
  const edges = [
    { from: 'wegovy',       to: 'patients', weight: 0.7 },
    { from: 'ozempic',      to: 'patients', weight: 0.5 },
    { from: 'tirzepatide',  to: 'patients', weight: 0.6 },
    { from: 'patients',     to: 'payers',   weight: 0.8 },
    { from: 'patients',     to: 'cms',      weight: 0.9, ghost: true },
    { from: 'orforglipron', to: 'patients', weight: 0.4, future: true },
    { from: 'retatrutide',  to: 'patients', weight: 0.3, future: true },
    { from: 'cagrisema',    to: 'patients', weight: 0.3, future: true },
    { from: 'maritide',     to: 'patients', weight: 0.2, future: true },
    { from: 'danuglipron',  to: 'patients', weight: 0.15, future: true },
    { from: 'fda',          to: 'wegovy',   weight: 0.3 },
  ];
  const getNode = (id: string) => nodes.find((n) => n.id === id);
  const W = 600, H = 440;

  return (
    <section
      aria-label="Digital Twin"
      className="flex flex-col"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-divider)',
        borderRadius: 12,
        padding: 18,
        maxHeight: 'calc(100vh - 280px)',
      }}
    >
      <header
        className="flex items-center justify-between"
        style={{ marginBottom: 12 }}
      >
        <div>
          <h2 className="font-display mz-text-lg" style={{ color: 'var(--color-ink)' }}>
            Digital Twin · GLP-1 Market
          </h2>
          <div
            className="mz-text-xs uppercase"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.1em', marginTop: 2 }}
          >
            POSTERIOR STATE · LIVE (BE-53 BACKING SOON)
          </div>
        </div>
        <div className="flex gap-3.5">
          {[
            { l: 'YOU',    v: '62%',   c: '#003b71' },
            { l: 'RIVALS', v: '32%',   c: '#d52b1e' },
            { l: 'CONF',   v: '0.79',  c: 'var(--color-accent)' },
          ].map((s) => (
            <div key={s.l} style={{ textAlign: 'right' }}>
              <div
                className="mz-text-xs uppercase"
                style={{ color: 'var(--color-ink-4)', letterSpacing: '0.1em', fontSize: 8 }}
              >
                {s.l}
              </div>
              <div
                className="font-mono"
                style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: s.c }}
              >
                {s.v}
              </div>
            </div>
          ))}
        </div>
      </header>

      <div
        className="flex-1 relative"
        style={{
          background: 'var(--color-bg)',
          borderRadius: 8,
          border: '1px solid var(--color-divider)',
          overflow: 'hidden',
          minHeight: 360,
        }}
      >
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }}>
          <defs>
            <pattern id="twingrid" width={40} height={40} patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--color-divider)" strokeWidth="0.5" opacity={0.3} />
            </pattern>
          </defs>
          <rect width={W} height={H} fill="url(#twingrid)" />
          {edges.map((e, i) => {
            const a = getNode(e.from), b = getNode(e.to);
            if (!a || !b) return null;
            return (
              <line
                key={i}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={e.future ? 'rgb(139,92,246)' : e.ghost ? 'rgb(245,158,11)' : 'var(--color-ink-4)'}
                strokeWidth={e.weight * 2.5}
                opacity={e.future ? 0.35 : 0.5}
                strokeDasharray={e.future || e.ghost ? '4 4' : undefined}
              />
            );
          })}
          {nodes.map((n) => (
            <g
              key={n.id}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoverNode(n.id)}
              onMouseLeave={() => setHoverNode(null)}
            >
              {n.pulsing && (
                <circle cx={n.x} cy={n.y} r={n.r + 4} fill={n.color} opacity={0.15}>
                  <animate attributeName="r" values={`${n.r + 2};${n.r + 12};${n.r + 2}`} dur="2.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.3;0;0.3" dur="2.5s" repeatCount="indefinite" />
                </circle>
              )}
              <circle
                cx={n.x} cy={n.y} r={n.r}
                fill={n.color}
                opacity={n.core ? 1 : 0.85}
                stroke={hoverNode === n.id ? 'var(--color-ink)' : 'transparent'}
                strokeWidth={2}
              />
              <text
                x={n.x} y={n.y + n.r + 13}
                textAnchor="middle"
                fill="var(--color-ink)" fontSize={9.5}
                fontWeight={n.core ? 600 : 500}
                fontFamily="DM Sans"
              >
                {n.label}
              </text>
              {n.share != null && (
                <text x={n.x} y={n.y + 3} textAnchor="middle" fill="#fff" fontSize={10} fontWeight={700} fontFamily="DM Mono">
                  {n.share}%
                </text>
              )}
              {n.phase && (
                <text x={n.x} y={n.y + n.r + 25} textAnchor="middle" fill="var(--color-ink-4)" fontSize={8} fontFamily="DM Mono">
                  {n.phase}
                </text>
              )}
            </g>
          ))}
        </svg>
        {hoverNode && (
          <div
            className="absolute mz-text-xs"
            style={{
              bottom: 10, left: 10,
              padding: '8px 12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-divider)',
              borderRadius: 8,
              maxWidth: 260,
              color: 'var(--color-ink)',
              fontSize: 11,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 3 }}>{getNode(hoverNode)?.label}</div>
            <div style={{ color: 'var(--color-ink-3)', lineHeight: 1.5, fontSize: 10 }}>
              {hoverNode === 'patients' && '~12.3M eligible US patients · 38% on therapy'}
              {hoverNode === 'orforglipron' && "Lilly oral · Twin posterior P(Q1 '27 launch) = 0.41"}
              {hoverNode === 'cms' && 'Draft NCD active · 19 days to comment close'}
              {!['patients', 'orforglipron', 'cms'].includes(hoverNode) && 'Click to FRAME AS DECISION'}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// ── Moments zone ───────────────────────────────────────────────

function MomentsZone({ moments, onOpen }: { moments: Moment[]; onOpen?: (m: Moment) => void }) {
  return (
    <section
      aria-label="AI Moments"
      className="flex flex-col gap-2.5"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-divider)',
        borderRadius: 12,
        padding: 18,
      }}
    >
      <header>
        <h2 className="font-display mz-text-lg" style={{ color: 'var(--color-ink)' }}>
          AI Moments
        </h2>
        <div
          className="mz-text-xs uppercase"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.1em', marginTop: 2 }}
        >
          RANKED BY EV × TIME-DECAY
        </div>
      </header>
      {moments.length === 0 ? (
        <p className="mz-text-sm" style={{ color: 'var(--color-ink-4)' }}>
          No moments synthesised yet. The synthesizer needs tier-1 signals to fire.
        </p>
      ) : (
        moments.map((m, i) => <MomentCard key={m.id} moment={m} idx={i} onClick={() => onOpen?.(m)} />)
      )}
    </section>
  );
}

function MomentCard({ moment, idx, onClick }: { moment: Moment; idx: number; onClick?: () => void }) {
  const cat = IMPACT_CATEGORIES.find((c) => c.id === moment.category) ?? IMPACT_CATEGORIES[2];
  const hours = moment.expires_hours;
  const urgencyColor =
    hours < 72 ? 'rgb(239,68,68)' :
    hours < 200 ? 'rgb(245,158,11)' :
    'var(--color-ink-3)';

  return (
    <article
      className="mz-elevated"
      onClick={onClick}
      style={{
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-divider)',
        borderRadius: 10,
        padding: 14,
        cursor: 'pointer',
      }}
    >
      <div className="flex items-center gap-1.5" style={{ marginBottom: 8 }}>
        <span className="font-mono mz-text-xs" style={{ color: 'var(--color-ink-4)', fontSize: 9 }}>
          MOMENT.{String(idx + 1).padStart(2, '0')}
        </span>
        <span
          className="mz-text-xs font-medium"
          style={{
            padding: '1px 6px',
            borderRadius: 4,
            background: `${cat.color}28`,
            color: cat.color,
            fontSize: 9,
          }}
        >
          {cat.label}
        </span>
        <span
          className="font-mono ml-auto mz-text-xs"
          style={{ color: urgencyColor, fontWeight: 600 }}
        >
          {hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`}
        </span>
      </div>
      <div className="mz-text-sm" style={{ color: 'var(--color-ink)', fontWeight: 500, lineHeight: 1.4, marginBottom: 10 }}>
        {moment.title}
      </div>
      <div className="flex items-center gap-3" style={{ marginBottom: 8 }}>
        <div>
          <div
            className="mz-text-xs uppercase"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em', fontSize: 8 }}
          >
            EV @ STAKE
          </div>
          <div className="font-mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-accent)' }}>
            {`$${moment.ev_at_stake_musd}M`}
          </div>
        </div>
        <div className="flex-1">
          <div
            className="mz-text-xs uppercase"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em', fontSize: 8, marginBottom: 3 }}
          >
            BELIEF Δ
          </div>
          <BeliefBar from={moment.delta_belief.from} to={moment.delta_belief.to} />
        </div>
      </div>
      <div className="flex gap-1">
        {moment.plays.map((p: Play) => (
          <div
            key={p.id}
            style={{
              flex: 1, height: 3, borderRadius: 1.5, opacity: 0.7,
              background:
                p.kind === 'aggressive' ? 'rgb(239,68,68)' :
                p.kind === 'balanced'   ? 'var(--color-accent)' :
                'rgb(34,197,94)',
            }}
          />
        ))}
      </div>
    </article>
  );
}

function BeliefBar({ from, to }: { from: number; to: number }) {
  return (
    <div
      style={{
        height: 4,
        background: 'var(--color-line)',
        borderRadius: 2,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: `${from * 100}%`,
          top: 0,
          bottom: 0,
          width: `${(to - from) * 100}%`,
          background: 'var(--color-accent)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: `${to * 100}%`,
          top: -2,
          bottom: -2,
          width: 2,
          background: 'var(--color-accent)',
        }}
      />
    </div>
  );
}

// ── Decision Ledger slide-over ─────────────────────────────────

function DecisionLedgerSlideOver({ close }: { close: () => void }) {
  const navigate = useNavigate();
  return (
    <div
      onClick={close}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.4)',
        zIndex: 250,
        display: 'flex', justifyContent: 'flex-end',
      }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 480, height: '100vh',
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-divider)',
          overflow: 'auto',
          padding: 24,
        }}
      >
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <div>
            <div
              className="mz-text-xs uppercase"
              style={{ color: 'var(--color-ink-4)', letterSpacing: '0.15em', marginBottom: 4 }}
            >
              DECISION LEDGER
            </div>
            <div className="font-display mz-text-xl" style={{ color: 'var(--color-ink)' }}>
              Recent Decisions
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: '1px solid var(--color-divider)',
              borderRadius: 6,
              width: 30, height: 30,
              color: 'var(--color-ink-3)',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>
        <p className="mz-text-sm" style={{ color: 'var(--color-ink-3)', marginBottom: 16 }}>
          Append-only commit record. Real briefs land here once BE-51 (DecisionFrame) wires through.
        </p>
        <button
          type="button"
          onClick={() => {
            close();
            navigate('/ci?tab=decisions');
          }}
          className="mz-text-sm"
          style={{
            width: '100%',
            padding: '10px 14px',
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-divider)',
            borderRadius: 8,
            color: 'var(--color-ink)',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          Open full ledger →
        </button>
      </aside>
    </div>
  );
}
