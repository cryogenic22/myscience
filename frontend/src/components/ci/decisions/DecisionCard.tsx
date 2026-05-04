import { useState } from 'react';
import { Target, ExternalLink, ChevronDown, ChevronRight, Search } from 'lucide-react';
import { decisionsApi, MOVE_TYPE_META, type Decision, type DecisionStatus } from '../../../api';
import DeadlineChip from './DeadlineChip';
import CalibrationChip from './CalibrationChip';
import OutcomeDetector from './OutcomeDetector';

interface Props {
  decision: Decision;
  onChange: (updated: Decision) => void;
  onOpenWarRoom?: (roomId: string) => void;
}

const STATUS_META: Record<DecisionStatus, { label: string; bg: string; fg: string }> = {
  open:        { label: 'Open',         bg: '#DBEAFE', fg: '#1E40AF' },
  in_progress: { label: 'In progress',  bg: '#FEF3C7', fg: '#A16207' },
  verified:    { label: 'Verified',     bg: '#DCFCE7', fg: '#15803D' },
  missed:      { label: 'Missed',       bg: '#FEE2E2', fg: '#B91C1C' },
  cancelled:   { label: 'Cancelled',    bg: 'var(--color-surface-2)', fg: 'var(--color-ink-4)' },
};

const STATUS_OPTIONS: DecisionStatus[] = ['open', 'in_progress', 'verified', 'missed', 'cancelled'];

function isOwner(d: Decision): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const tok = window.localStorage.getItem('mz_auth_token');
    if (!tok) return false;
    const payload = tok.split('.')[1];
    if (!payload) return false;
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded));
    return decoded?.sub === d.owner_user_id;
  } catch {
    return false;
  }
}

export default function DecisionCard({ decision, onChange, onOpenWarRoom }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const owner = isOwner(decision);
  const meta = STATUS_META[decision.status];
  const moveMeta = MOVE_TYPE_META[decision.move_type];
  const canDetectOutcome = owner && ['open', 'in_progress'].includes(decision.status);

  const handleStatus = async (next: DecisionStatus) => {
    setBusy(true);
    try {
      const updated = await decisionsApi.patch(decision.id, { status: next });
      onChange(updated);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${meta.fg}`,
        borderRadius: '6px',
        padding: '14px 16px',
        background: 'var(--color-surface)',
      }}
    >
      <div className="flex items-start gap-3 mb-2">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          style={{ background: 'transparent', border: 'none', color: 'var(--color-ink-4)', padding: '2px' }}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-2 mb-1">
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '2px 7px',
                borderRadius: '4px',
                background: meta.bg,
                color: meta.fg,
                letterSpacing: '0.05em',
              }}
            >
              {meta.label}
            </span>
            <DeadlineChip
              deadline={decision.deadline}
              daysToDeadline={decision.days_to_deadline}
              overdue={decision.overdue}
              status={decision.status}
            />
            <CalibrationChip score={decision.calibration_score} />
            <span style={{ fontSize: '12px' }}>{moveMeta?.icon}</span>
            <span className="text-[10px]" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}>
              {moveMeta?.label ?? decision.move_type}
            </span>
            <span className="text-[10px] ml-auto" style={{ color: 'var(--color-ink-4)' }}>
              {decision.created_at ? new Date(decision.created_at).toLocaleDateString() : ''}
            </span>
          </div>
          <div className="text-[14px] font-medium" style={{ color: 'var(--color-ink)' }}>
            {decision.title}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
            <Target size={10} className="inline mr-1" />
            <span>{decision.owner_display_name}</span>
            {decision.target_metric && (
              <span> · {decision.target_metric}{decision.target_value && `: ${decision.target_value}`}</span>
            )}
            {typeof decision.confidence_at_commit === 'number' && (
              <span> · committed at {(decision.confidence_at_commit * 100).toFixed(0)}% confidence</span>
            )}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pl-6 space-y-3">
          {decision.rationale && (
            <div
              className="text-[12px] leading-relaxed"
              style={{ color: 'var(--color-ink-2)' }}
            >
              {decision.rationale}
            </div>
          )}

          {decision.actual_outcome && (
            <div
              className="text-[11px] p-3"
              style={{
                background: 'var(--color-surface-2)',
                borderRadius: '6px',
                color: 'var(--color-ink-2)',
              }}
            >
              <div
                className="text-[10px] uppercase font-medium mb-1"
                style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
              >
                Actual outcome
                {decision.actual_outcome_recorded_at && ` · recorded ${new Date(decision.actual_outcome_recorded_at).toLocaleDateString()}`}
              </div>
              {decision.actual_outcome}
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            {decision.war_room_id && onOpenWarRoom && (
              <button
                type="button"
                onClick={() => onOpenWarRoom(decision.war_room_id!)}
                className="text-[11px] inline-flex items-center gap-1"
                style={{
                  padding: '4px 10px',
                  borderRadius: '4px',
                  background: 'transparent',
                  color: 'var(--color-ink-3)',
                  border: '1px solid var(--color-line)',
                  cursor: 'pointer',
                }}
              >
                <ExternalLink size={10} />
                Open source war room
              </button>
            )}
            {canDetectOutcome && (
              <button
                type="button"
                onClick={() => setDetecting(true)}
                className="text-[11px] inline-flex items-center gap-1 font-medium"
                style={{
                  padding: '4px 10px',
                  borderRadius: '4px',
                  background: 'var(--color-accent)',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                }}
                title="Run the outcome matcher: scan recent signals for an outcome that matches this decision"
              >
                <Search size={10} />
                Detect outcome
              </button>
            )}
          </div>

          {detecting && (
            <OutcomeDetector
              decision={decision}
              onClose={() => setDetecting(false)}
              onCaptured={(updated) => {
                setDetecting(false);
                onChange(updated);
              }}
            />
          )}

          {owner && (
            <div className="flex items-center gap-1 flex-wrap">
              <span
                className="text-[10px] uppercase font-medium"
                style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em', marginRight: '4px' }}
              >
                Set status:
              </span>
              {STATUS_OPTIONS.map((s) => {
                const sm = STATUS_META[s];
                const active = s === decision.status;
                return (
                  <button
                    key={s}
                    type="button"
                    disabled={busy || active}
                    onClick={() => handleStatus(s)}
                    className="text-[10px]"
                    style={{
                      padding: '3px 8px',
                      borderRadius: '4px',
                      background: active ? sm.bg : 'transparent',
                      color: active ? sm.fg : 'var(--color-ink-3)',
                      border: `1px solid ${active ? sm.fg : 'var(--color-line)'}`,
                      cursor: active || busy ? 'default' : 'pointer',
                      opacity: busy ? 0.5 : 1,
                    }}
                  >
                    {sm.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
