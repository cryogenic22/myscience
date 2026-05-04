import { Calendar, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface Props {
  deadline: string | null;
  daysToDeadline: number | null;
  overdue: boolean;
  status: string;
}

/** Small chip rendering a decision's deadline with color coded urgency. */
export default function DeadlineChip({ deadline, daysToDeadline, overdue, status }: Props) {
  if (!deadline) {
    return (
      <span
        className="text-[10px] inline-flex items-center gap-1"
        style={{
          padding: '2px 7px',
          borderRadius: '4px',
          background: 'var(--color-surface-2)',
          color: 'var(--color-ink-4)',
        }}
        title="No deadline set"
      >
        <Calendar size={10} />
        no deadline
      </span>
    );
  }

  // Decision is closed: just show the date, no urgency styling
  if (!['open', 'in_progress'].includes(status)) {
    return (
      <span
        className="text-[10px] inline-flex items-center gap-1"
        style={{
          padding: '2px 7px',
          borderRadius: '4px',
          background: 'var(--color-surface-2)',
          color: 'var(--color-ink-4)',
        }}
      >
        <CheckCircle2 size={10} />
        was {new Date(deadline).toLocaleDateString()}
      </span>
    );
  }

  // Active decision: color by urgency
  let bg = '#DCFCE7';   // green (>14d)
  let fg = '#15803D';
  let icon = <Calendar size={10} />;
  let label = '';

  if (overdue) {
    bg = '#FEE2E2';
    fg = '#B91C1C';
    icon = <AlertTriangle size={10} />;
    label = `overdue ${Math.abs(daysToDeadline ?? 0)}d`;
  } else if (daysToDeadline !== null && daysToDeadline <= 14) {
    bg = '#FEF3C7';
    fg = '#A16207';
    icon = <AlertTriangle size={10} />;
    label = `due in ${daysToDeadline}d`;
  } else if (daysToDeadline !== null) {
    label = `due in ${daysToDeadline}d`;
  } else {
    label = new Date(deadline).toLocaleDateString();
  }

  return (
    <span
      className="text-[10px] inline-flex items-center gap-1 font-medium"
      style={{
        padding: '2px 7px',
        borderRadius: '4px',
        background: bg,
        color: fg,
      }}
      title={`Deadline: ${new Date(deadline).toLocaleDateString()}`}
    >
      {icon}
      {label}
    </span>
  );
}
