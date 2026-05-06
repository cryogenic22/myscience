import { Link2, Sparkles, Swords, Target } from 'lucide-react';

interface Props {
  /** "Born from" signal — the seed that started the chain */
  sourceSignal?: {
    id: string;
    headline: string;
  } | null;
  /** Originating war room */
  warRoom?: {
    id: string;
    title: string;
  } | null;
  /** This-is-here marker (e.g. "Decision: X") */
  current?: {
    label: string;  // "Decision" | "Round" | "Outcome"
    title: string;
  };
  onOpenSignal?: (id: string) => void;
  onOpenWarRoom?: (id: string) => void;
  /** Compact one-line variant for cards; verbose for full pages */
  variant?: 'compact' | 'verbose';
}

/** Renders the agentic-loop provenance trail:
 *    Signal → War Room → Decision (or whatever the current node is)
 *
 * Each upstream step is clickable when a callback is provided.
 * Closes the running coverage-audit gap "source_signal_id stored,
 * not linked back in UI" called out across phases B/C/D.
 */
export default function ProvenanceTrail({
  sourceSignal, warRoom, current,
  onOpenSignal, onOpenWarRoom, variant = 'compact',
}: Props) {
  if (!sourceSignal && !warRoom && !current) return null;

  if (variant === 'verbose') {
    return (
      <div
        style={{
          padding: '12px 14px',
          borderRadius: '6px',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-line)',
        }}
      >
        <div
          className="text-[10px] uppercase font-medium mb-2 inline-flex items-center gap-1"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
        >
          <Link2 size={10} />
          Provenance
        </div>
        <div className="space-y-1.5">
          {sourceSignal && (
            <Step
              icon={<Sparkles size={12} style={{ color: '#15803D' }} />}
              label="Born from signal"
              title={sourceSignal.headline}
              onClick={onOpenSignal && (() => onOpenSignal(sourceSignal.id))}
            />
          )}
          {warRoom && (
            <Step
              icon={<Swords size={12} style={{ color: 'var(--color-accent)' }} />}
              label="In war room"
              title={warRoom.title}
              onClick={onOpenWarRoom && (() => onOpenWarRoom(warRoom.id))}
            />
          )}
          {current && (
            <Step
              icon={<Target size={12} style={{ color: 'var(--color-ink-3)' }} />}
              label={current.label}
              title={current.title}
              onClick={undefined}
              isCurrent
            />
          )}
        </div>
      </div>
    );
  }

  // Compact one-line variant for cards
  return (
    <div
      className="text-[10px] inline-flex items-center gap-1 flex-wrap"
      style={{ color: 'var(--color-ink-4)' }}
    >
      <Link2 size={10} />
      {sourceSignal && (
        <>
          <span>From</span>
          {onOpenSignal ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onOpenSignal(sourceSignal.id); }}
              style={{
                background: 'transparent', border: 'none', padding: 0,
                color: 'var(--color-accent)', cursor: 'pointer',
                textDecoration: 'underline', fontSize: 'inherit',
              }}
            >
              "{truncate(sourceSignal.headline, 40)}"
            </button>
          ) : (
            <span style={{ color: 'var(--color-ink-3)' }}>"{truncate(sourceSignal.headline, 40)}"</span>
          )}
        </>
      )}
      {sourceSignal && warRoom && <span>→</span>}
      {warRoom && (
        <>
          <span>{!sourceSignal && 'In '}room</span>
          {onOpenWarRoom ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onOpenWarRoom(warRoom.id); }}
              style={{
                background: 'transparent', border: 'none', padding: 0,
                color: 'var(--color-accent)', cursor: 'pointer',
                textDecoration: 'underline', fontSize: 'inherit',
              }}
            >
              "{truncate(warRoom.title, 30)}"
            </button>
          ) : (
            <span style={{ color: 'var(--color-ink-3)' }}>"{truncate(warRoom.title, 30)}"</span>
          )}
        </>
      )}
    </div>
  );
}

function Step({
  icon, label, title, onClick, isCurrent,
}: {
  icon: React.ReactNode;
  label: string;
  title: string;
  onClick?: () => void;
  isCurrent?: boolean;
}) {
  return (
    <div className="flex items-start gap-2">
      <div style={{ marginTop: '2px' }}>{icon}</div>
      <div className="flex-1">
        <div
          className="text-[10px] uppercase font-medium"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.04em' }}
        >
          {label}
        </div>
        {onClick ? (
          <button
            type="button"
            onClick={onClick}
            className="text-[12px] text-left"
            style={{
              background: 'transparent', border: 'none', padding: 0,
              color: 'var(--color-accent)',
              textDecoration: 'underline',
              cursor: 'pointer',
            }}
          >
            {title}
          </button>
        ) : (
          <div
            className="text-[12px]"
            style={{ color: isCurrent ? 'var(--color-ink)' : 'var(--color-ink-2)' }}
          >
            {title}
          </div>
        )}
      </div>
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
