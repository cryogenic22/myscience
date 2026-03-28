import { useEffect, useRef, useState } from 'react';

interface QueryProgressProps {
  status: string | null;
  visible: boolean;
}

interface ProgressStage {
  label: string;
  percent: number;
}

function mapStatusToStage(status: string): ProgressStage {
  const lower = status.toLowerCase();
  if (lower.includes('understand') || lower.includes('intent')) {
    return { label: 'Understanding your question...', percent: 25 };
  }
  if (lower.includes('retriev') || lower.includes('search') || lower.includes('fetch')) {
    return { label: 'Retrieving evidence...', percent: 50 };
  }
  if (lower.includes('reason') || lower.includes('analyz') || lower.includes('graph')) {
    return { label: 'Reasoning over data...', percent: 75 };
  }
  if (lower.includes('synthe') || lower.includes('generat') || lower.includes('stream')) {
    return { label: 'Generating response...', percent: 90 };
  }
  return { label: status, percent: 50 };
}

const TIMER_STAGES: Array<{ at: number; label: string; percent: number }> = [
  { at: 0, label: 'Understanding your question...', percent: 25 },
  { at: 1000, label: 'Retrieving evidence...', percent: 50 },
  { at: 3000, label: 'Reasoning over data...', percent: 75 },
  { at: 5000, label: 'Generating response...', percent: 90 },
];

export default function QueryProgress({ status, visible }: QueryProgressProps) {
  const [timerStage, setTimerStage] = useState<ProgressStage>(TIMER_STAGES[0]);
  const [opacity, setOpacity] = useState(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const startTimeRef = useRef<number>(0);
  const hasReceivedStatus = useRef(false);

  // Track whether we've received real status updates from the backend
  useEffect(() => {
    if (status) {
      hasReceivedStatus.current = true;
    }
  }, [status]);

  // Timer-based fallback progress
  useEffect(() => {
    if (visible) {
      startTimeRef.current = Date.now();
      hasReceivedStatus.current = false;
      setTimerStage(TIMER_STAGES[0]);

      const timers = TIMER_STAGES.slice(1).map((stage) =>
        setTimeout(() => {
          if (!hasReceivedStatus.current) {
            setTimerStage({ label: stage.label, percent: stage.percent });
          }
        }, stage.at),
      );
      timersRef.current = timers;
    }

    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, [visible]);

  // Fade in/out
  useEffect(() => {
    if (visible) {
      // Small delay so the DOM renders at opacity 0 first
      const id = requestAnimationFrame(() => setOpacity(1));
      return () => cancelAnimationFrame(id);
    } else {
      setOpacity(0);
    }
  }, [visible]);

  if (!visible && opacity === 0) return null;

  const stage = status ? mapStatusToStage(status) : timerStage;

  return (
    <div
      style={{
        opacity,
        transition: 'opacity 300ms ease',
        padding: '10px 0 0 0',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          background: 'var(--color-surface-2)',
          borderRadius: '8px',
          padding: '8px 14px',
          height: '36px',
        }}
      >
        <span
          style={{
            fontSize: '12px',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-ink-3)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            flex: '1 1 auto',
            minWidth: 0,
          }}
        >
          {stage.label}
        </span>
        <div
          style={{
            flex: '0 0 100px',
            height: '4px',
            borderRadius: '2px',
            background: 'var(--color-surface-3)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${stage.percent}%`,
              height: '100%',
              borderRadius: '2px',
              background: 'var(--color-accent)',
              transition: 'width 600ms cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          />
        </div>
        <span
          style={{
            fontSize: '11px',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-ink-4)',
            flex: '0 0 auto',
            minWidth: '28px',
            textAlign: 'right',
          }}
        >
          {stage.percent}%
        </span>
      </div>
    </div>
  );
}
