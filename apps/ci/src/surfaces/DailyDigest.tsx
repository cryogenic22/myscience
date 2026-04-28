import { Card, Pill, ScoreTile, KbqTag, type Kbq } from '@pulse/ui';

type Tier = 'high' | 'medium' | 'low';
type Confidence = 'confirmed' | 'reported' | 'inferred' | 'disputed';

interface MockSignal {
  id: string;
  entity: string;
  eventType: string;
  kbq: Kbq;
  impact: Tier;
  confidence: Confidence;
  summary: string;
  sources: string[];
  age: string;
}

const SIGNALS: MockSignal[] = [
  {
    id: 's1', entity: 'Pfizer', eventType: 'EXEC TRANSITION',
    kbq: 'governance', impact: 'high', confidence: 'confirmed',
    summary: 'CMO Mikael Dolsten transitions to Strategic Advisor; successor to be named within 90d.',
    sources: ['edgar:0', 'press:1'], age: '2h',
  },
  {
    id: 's2', entity: 'Novo Nordisk', eventType: 'CHMP POSITIVE OPINION',
    kbq: 'regulatory', impact: 'high', confidence: 'confirmed',
    summary: 'CHMP issues positive opinion on semaglutide cardiovascular indication; EC decision ~60d.',
    sources: ['ema:0', 'press:1', 'news:2'], age: '6h',
  },
  {
    id: 's3', entity: 'Bristol Myers Squibb', eventType: 'LICENSE-IN DEAL',
    kbq: 'm_and_a', impact: 'high', confidence: 'confirmed',
    summary: '$50M upfront / up to $500M milestones for KRAS G12C asset from Pivotal Bio.',
    sources: ['edgar:0', 'press:1', 'news:2', 'news:3'], age: '9h',
  },
  {
    id: 's4', entity: 'Eli Lilly', eventType: 'TRIAL STATUS · PHASE 3',
    kbq: 'clinical', impact: 'medium', confidence: 'confirmed',
    summary: 'NCT05726227 SURMOUNT-MMO primary completion advanced to Q3 2026; readout expected Q4.',
    sources: ['ct_gov:0', 'press:1'], age: '14h',
  },
  {
    id: 's5', entity: 'Moderna', eventType: 'GUIDANCE CHANGE',
    kbq: 'financial', impact: 'medium', confidence: 'reported',
    summary: 'Trade press reports FY26 revenue guidance raised; awaiting 8-K filing for confirmation.',
    sources: ['news:0', 'news:1'], age: '18h',
  },
];

export function DailyDigest() {
  return (
    <div>
      <div style={{ marginBottom: 'var(--mz-space-6)' }}>
        <h1
          style={{
            fontFamily: 'var(--mz-font-display)',
            fontSize: 'var(--mz-text-display-2)',
            fontWeight: 'var(--mz-weight-semibold)',
            letterSpacing: 'var(--mz-tracking-tight)',
            margin: 0,
          }}
        >
          Daily Digest
        </h1>
        <div
          style={{
            color: 'var(--mz-color-text-secondary)',
            fontSize: 'var(--mz-text-body-2)',
            marginTop: 'var(--mz-space-1)',
          }}
        >
          {SIGNALS.length} signals across your watchlist · last 24h
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 'var(--mz-space-3)',
          marginBottom: 'var(--mz-space-6)',
        }}
      >
        <ScoreTile label="SIGNALS · 24H"  value={12} trend="up"   trendValue="+3" caption="across watchlist" />
        <ScoreTile label="HIGH IMPACT"    value={3}  trend="up"   trendValue="+1" caption="vs yesterday" />
        <ScoreTile label="REVIEWER QUEUE" value={4}  trend="flat" trendValue="0"  caption="depth" />
        <ScoreTile label="GUARD PASS"     value="89%" caption="hallucination guard" />
      </div>

      <div
        style={{
          fontFamily: 'var(--mz-font-mono)',
          fontSize: 'var(--mz-text-mono-2)',
          color: 'var(--mz-color-text-tertiary)',
          letterSpacing: 'var(--mz-tracking-wide)',
          textTransform: 'uppercase',
          marginBottom: 'var(--mz-space-2)',
        }}
      >
        Sorted by impact
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--mz-space-2)' }}>
        {SIGNALS.map((s) => (
          <SignalRow key={s.id} signal={s} />
        ))}
      </div>

      <KeyboardHints />
    </div>
  );
}

function SignalRow({ signal }: { signal: MockSignal }) {
  const impactTone = signal.impact === 'high' ? 'danger' : signal.impact === 'medium' ? 'warning' : 'neutral';
  const confTone =
    signal.confidence === 'confirmed' ? 'success' :
    signal.confidence === 'inferred'  ? 'warning' :
    signal.confidence === 'disputed'  ? 'danger'  : 'neutral';

  return (
    <Card variant="interactive" onClick={() => {}}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          alignItems: 'flex-start',
          gap: 'var(--mz-space-4)',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--mz-space-2)',
              marginBottom: 'var(--mz-space-1)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--mz-font-display)',
                fontWeight: 'var(--mz-weight-semibold)',
                fontSize: 'var(--mz-text-headline-3)',
                color: 'var(--mz-color-text-primary)',
              }}
            >
              {signal.entity}
            </span>
            <span style={{ color: 'var(--mz-color-text-tertiary)' }}>·</span>
            <span
              style={{
                fontFamily: 'var(--mz-font-mono)',
                fontSize: 'var(--mz-text-mono-2)',
                color: 'var(--mz-color-text-secondary)',
                letterSpacing: 'var(--mz-tracking-wide)',
              }}
            >
              {signal.eventType}
            </span>
            <KbqTag kbq={signal.kbq} short />
          </div>
          <div
            style={{
              fontSize: 'var(--mz-text-body-2)',
              color: 'var(--mz-color-text-primary)',
              lineHeight: 'var(--mz-leading-normal)',
            }}
          >
            {signal.summary}
          </div>
          <div
            style={{
              marginTop: 'var(--mz-space-2)',
              display: 'flex',
              gap: 'var(--mz-space-1)',
              flexWrap: 'wrap',
            }}
          >
            {signal.sources.map((src) => (
              <Pill key={src} tone="neutral" subtle size="sm">
                {src}
              </Pill>
            ))}
          </div>
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 'var(--mz-space-1)',
            flexShrink: 0,
          }}
        >
          <Pill tone={impactTone} size="sm">{signal.impact.toUpperCase()}</Pill>
          <Pill tone={confTone}   size="sm" subtle>{signal.confidence.toUpperCase()}</Pill>
          <span
            style={{
              fontFamily: 'var(--mz-font-mono)',
              fontSize: 'var(--mz-text-mono-3)',
              color: 'var(--mz-color-text-tertiary)',
              letterSpacing: 'var(--mz-tracking-wide)',
              marginTop: 'var(--mz-space-1)',
            }}
          >
            {signal.age} ago
          </span>
        </div>
      </div>
    </Card>
  );
}

function KeyboardHints() {
  const hints: Array<{ key: string; label: string }> = [
    { key: 'j / k', label: 'navigate' },
    { key: '↵',     label: 'open' },
    { key: 'e',     label: 'escalate' },
    { key: 'f',     label: 'follow up' },
    { key: 'x',     label: 'dismiss' },
  ];
  return (
    <div
      style={{
        marginTop: 'var(--mz-space-8)',
        paddingTop: 'var(--mz-space-3)',
        borderTop: '1px solid var(--mz-color-border-subtle)',
        display: 'flex',
        gap: 'var(--mz-space-4)',
        fontFamily: 'var(--mz-font-mono)',
        fontSize: 'var(--mz-text-mono-3)',
        color: 'var(--mz-color-text-tertiary)',
        letterSpacing: 'var(--mz-tracking-wide)',
        flexWrap: 'wrap',
      }}
    >
      {hints.map((h) => (
        <span key={h.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <kbd
            style={{
              background: 'var(--mz-color-surface)',
              border: '1px solid var(--mz-color-border-subtle)',
              borderRadius: 4,
              padding: '0 4px',
              fontFamily: 'inherit',
            }}
          >
            {h.key}
          </kbd>
          {h.label}
        </span>
      ))}
    </div>
  );
}
