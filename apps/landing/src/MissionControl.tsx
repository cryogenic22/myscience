import { useEffect, useState } from 'react';
import { Card, Pill, ScoreTile } from '@mz/ui';
import { ModuleCard } from './components/ModuleCard';
import { RecentActivity } from './components/RecentActivity';
import { Header } from './components/Header';
import { CommandPaletteStub } from './components/CommandPaletteStub';

/**
 * Mission Control — the platform's first screen.
 *
 * SPEC-016 §3. The user lands here, sees their accessible modules,
 * platform health at a glance, and recent activity across modules.
 *
 * This is a SKELETON: data is mocked. Wiring to the platform API
 * (`/catalog/health`, `/intel/health`, `/recent-activity`) is part of
 * Phase 0 task P0.9 and lands when those endpoints exist.
 */
export function MissionControl() {
  const [now, setNow] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
      if (e.key === 'Escape') setPaletteOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--mz-color-canvas)',
        color: 'var(--mz-color-text-primary)',
      }}
    >
      <Header onOpenPalette={() => setPaletteOpen(true)} />

      <main
        style={{
          maxWidth: 1180,
          margin: '0 auto',
          padding: 'var(--mz-space-12) var(--mz-space-6) var(--mz-space-16)',
        }}
      >
        <Greeting now={now} />

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
            gap: 'var(--mz-space-4)',
            marginTop: 'var(--mz-space-8)',
          }}
        >
          <ModuleCard
            module="ci"
            title="Competitive Intelligence"
            tagline="Triage, brief, alert."
            stats={[
              { label: 'NEW SIGNALS', value: '12' },
              { label: 'HIGH IMPACT', value: '2' },
              { label: 'IN QUEUE',    value: '4' },
            ]}
            status={{ tone: 'success', label: 'WATCHLIST HEALTHY' }}
            href="/ci"
          />
          <ModuleCard
            module="research"
            title="Pharma Research Intelligence"
            tagline="Ask the graph. Get cited answers."
            stats={[
              { label: 'ACTIVE RUNS',  value: '3' },
              { label: 'MEMORY',       value: '14' },
              { label: 'LAST QUERY',   value: '4h' },
            ]}
            status={{ tone: 'neutral', label: 'GLP-1 CARDIO …' }}
            href="/research"
          />
        </section>

        <section style={{ marginTop: 'var(--mz-space-12)' }}>
          <SectionHeading>Platform</SectionHeading>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--mz-space-3)',
              marginTop: 'var(--mz-space-3)',
            }}
          >
            <ScoreTile label="CATALOG FRESHNESS" value="✓" caption="all sources < 24h" />
            <ScoreTile label="SIGNALS · 7D"      value={612} trend="up" trendValue="+47" />
            <ScoreTile label="GUARD PASS"        value="89%" caption="hallucination guard" />
            <ScoreTile label="LLM SPEND"         value="$1,847" caption="of $5,000 cap" />
          </div>
        </section>

        <section style={{ marginTop: 'var(--mz-space-12)' }}>
          <SectionHeading>Recent across modules</SectionHeading>
          <Card style={{ marginTop: 'var(--mz-space-3)', padding: 0 }}>
            <RecentActivity />
          </Card>
        </section>
      </main>

      {paletteOpen && (
        <CommandPaletteStub onClose={() => setPaletteOpen(false)} />
      )}
    </div>
  );
}

function Greeting({ now }: { now: Date }) {
  const hour = now.getHours();
  const greeting =
    hour < 5  ? 'Good night' :
    hour < 12 ? 'Good morning' :
    hour < 18 ? 'Good afternoon' : 'Good evening';
  const dateStr = now.toLocaleDateString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric',
  });
  const timeStr = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  return (
    <div>
      <h1
        style={{
          fontFamily: 'var(--mz-font-display)',
          fontSize: 'var(--mz-text-display-1)',
          fontWeight: 'var(--mz-weight-semibold)',
          letterSpacing: 'var(--mz-tracking-tight)',
          margin: 0,
          lineHeight: 'var(--mz-leading-tight)',
        }}
      >
        {greeting}.
      </h1>
      <div
        style={{
          marginTop: 'var(--mz-space-2)',
          color: 'var(--mz-color-text-secondary)',
          fontSize: 'var(--mz-text-body-2)',
        }}
      >
        {dateStr} · {timeStr}
        <Pill tone="neutral" subtle size="sm" leading={<span aria-hidden>●</span>}>
          <span style={{ marginLeft: 4 }}>Phase 0</span>
        </Pill>
      </div>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        margin: 0,
        fontFamily: 'var(--mz-font-mono)',
        fontSize: 'var(--mz-text-mono-2)',
        color: 'var(--mz-color-text-tertiary)',
        letterSpacing: 'var(--mz-tracking-wide)',
        textTransform: 'uppercase',
        fontWeight: 'var(--mz-weight-medium)',
      }}
    >
      {children}
    </h2>
  );
}
