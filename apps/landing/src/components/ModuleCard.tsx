import { Card, Pill, type PillTone } from '@pulse/ui';

export interface ModuleStat {
  label: string;
  value: string;
}

export interface ModuleStatus {
  tone: PillTone;
  label: string;
}

export interface ModuleCardProps {
  module: 'ci' | 'research' | 'regulatory';
  title: string;
  tagline: string;
  stats: ModuleStat[];
  status: ModuleStatus;
  href: string;
}

/**
 * ModuleCard — primary affordance on Mission Control.
 * One per module the user has access to. Single number per stat.
 */
export function ModuleCard({ module, title, tagline, stats, status, href }: ModuleCardProps) {
  return (
    <div data-module={module}>
      <Card
        variant="interactive"
        onClick={() => { window.location.href = href; }}
        style={{ padding: 'var(--mz-space-6)', minHeight: 196 }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 'var(--mz-space-3)',
          }}
        >
          <Pill tone="accent" subtle size="sm">{module.toUpperCase()}</Pill>
          <Pill tone={status.tone} subtle size="sm">{status.label}</Pill>
        </div>

        <div
          style={{
            fontFamily: 'var(--mz-font-display)',
            fontSize: 'var(--mz-text-headline-1)',
            fontWeight: 'var(--mz-weight-semibold)',
            letterSpacing: 'var(--mz-tracking-tight)',
            color: 'var(--mz-color-text-primary)',
            marginBottom: 'var(--mz-space-1)',
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 'var(--mz-text-body-3)',
            color: 'var(--mz-color-text-secondary)',
            marginBottom: 'var(--mz-space-6)',
          }}
        >
          {tagline}
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${stats.length}, 1fr)`,
            gap: 'var(--mz-space-3)',
            marginBottom: 'var(--mz-space-4)',
          }}
        >
          {stats.map((s) => (
            <div key={s.label}>
              <div
                style={{
                  fontFamily: 'var(--mz-font-mono)',
                  fontSize: 'var(--mz-text-mono-3)',
                  letterSpacing: 'var(--mz-tracking-wide)',
                  color: 'var(--mz-color-text-tertiary)',
                  textTransform: 'uppercase',
                  marginBottom: 2,
                }}
              >
                {s.label}
              </div>
              <div
                style={{
                  fontFamily: 'var(--mz-font-display)',
                  fontSize: 'var(--mz-text-headline-1)',
                  fontWeight: 'var(--mz-weight-semibold)',
                  letterSpacing: 'var(--mz-tracking-tight)',
                  color: 'var(--mz-color-accent)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {s.value}
              </div>
            </div>
          ))}
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: 'var(--mz-space-3)',
            borderTop: '1px solid var(--mz-color-border-subtle)',
            color: 'var(--mz-color-accent)',
            fontSize: 'var(--mz-text-body-3)',
            fontWeight: 'var(--mz-weight-medium)',
          }}
        >
          <span>Open {title.split(' ').at(0)} →</span>
        </div>
      </Card>
    </div>
  );
}
