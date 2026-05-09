import { useState } from 'react';
import type { DecisionBrief, DecisionBriefPatchBody, DecisionBriefOptionInput } from '../../../api';
import StateMachineChip from './StateMachineChip';
import BriefEditableField from './BriefEditableField';
import OptionEditor from './OptionEditor';

/**
 * SPEC_030 §8.3 + §8.5 — top panel of DecisionWorkspace.
 *
 * Renders the brief's question (Syne display, inline-editable in
 * draft/human_review), state chip, time horizon, stakeholders, trigger,
 * confidence, and the options list with add/remove affordances per the
 * affordance matrix.
 */

const EDITABLE_STATES = new Set(['draft', 'human_review']);

interface Props {
  brief: DecisionBrief;
  onPatch: (patch: DecisionBriefPatchBody) => Promise<DecisionBrief> | void | Promise<void>;
  onAddOption: (opt: DecisionBriefOptionInput) => Promise<unknown> | void | Promise<void>;
  onRemoveOption?: (optionId: string) => Promise<unknown> | void;
}

function getRole(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('mz_auth_role');
}

export default function BriefPanel({ brief, onPatch, onAddOption, onRemoveOption }: Props) {
  const [showOptionEditor, setShowOptionEditor] = useState(false);

  const role = getRole();
  const writable = role === 'uploader' || role === 'enterprise';
  const editable = writable && EDITABLE_STATES.has(brief.state);
  const locked = !editable;

  return (
    <section
      data-testid="panel-brief"
      tabIndex={-1}
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-panel, 16px)',
        padding: 'var(--space-panel-pad, 24px)',
        boxShadow: 'var(--shadow-workspace-panel, var(--shadow-sm))',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-panel-gap, 16px)',
      }}
    >
      {/* Question — inline-editable in editable states */}
      <h1
        style={{
          margin: 0,
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(22px, 2.4vw, 32px)',
          fontWeight: 600,
          letterSpacing: '-0.02em',
          lineHeight: 1.15,
          color: 'var(--color-ink)',
        }}
      >
        <BriefEditableField
          value={brief.question}
          label="question"
          locked={locked}
          onSave={async (next) => {
            await onPatch({ question: next });
          }}
          multiline
        />
      </h1>

      {/* State chip + meta row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 12,
          fontSize: 12,
          color: 'var(--color-ink-2)',
          fontFamily: 'var(--font-body)',
        }}
      >
        <StateMachineChip state={brief.state} />
        {brief.time_horizon_days != null && (
          <span>
            <span style={{ color: 'var(--color-ink-3)' }}>Time horizon: </span>
            <strong>{brief.time_horizon_days} day{brief.time_horizon_days === 1 ? '' : 's'}</strong>
          </span>
        )}
        {brief.stakeholders.length > 0 && (
          <span>
            <span style={{ color: 'var(--color-ink-3)' }}>Stakeholders: </span>
            <strong>{brief.stakeholders.join(' · ')}</strong>
          </span>
        )}
        <span>
          <span style={{ color: 'var(--color-ink-3)' }}>Trigger: </span>
          <strong>{brief.trigger_kind}</strong>
        </span>
        {brief.confidence_to_proceed != null && (
          <span>
            <span style={{ color: 'var(--color-ink-3)' }}>Confidence to proceed: </span>
            <strong style={{ fontFamily: 'var(--font-mono)' }}>{brief.confidence_to_proceed.toFixed(2)}</strong>
          </span>
        )}
      </div>

      {/* Options strip */}
      <div
        style={{
          paddingTop: 'var(--space-panel-gap, 16px)',
          borderTop: '1px solid var(--color-line)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
            }}
          >
            Options ({brief.options.length} / 5)
          </span>
          <button
            type="button"
            disabled={!editable}
            aria-disabled={!editable}
            onClick={() => setShowOptionEditor(true)}
            className="btn btn-secondary btn-sm"
          >
            + add option
          </button>
        </div>

        {brief.options.length === 0 && (
          <div
            style={{
              fontSize: 13,
              color: 'var(--color-ink-3)',
              padding: '12px 0',
              fontStyle: 'italic',
            }}
          >
            No options yet — add one to begin.
          </div>
        )}

        {brief.options
          .slice()
          .sort((a, b) => a.ordinal - b.ordinal)
          .map((opt) => (
            <article
              key={opt.option_id}
              style={{
                background: 'var(--color-surface-2)',
                borderRadius: 'var(--radius-card, 12px)',
                padding: '12px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--color-accent)',
                    minWidth: 18,
                  }}
                >
                  {opt.ordinal}.
                </span>
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                    flex: 1,
                  }}
                >
                  {opt.label}
                </span>
                {editable && onRemoveOption && (
                  <button
                    type="button"
                    onClick={() => void onRemoveOption(opt.option_id)}
                    className="btn btn-ghost btn-xs"
                    aria-label={`remove option ${opt.label}`}
                    style={{ color: 'var(--color-ink-4)' }}
                  >
                    ×
                  </button>
                )}
              </div>
              {(opt.predicted_outcome || opt.cost_estimate) && (
                <div style={{ fontSize: 12, color: 'var(--color-ink-2)', paddingLeft: 26 }}>
                  {opt.predicted_outcome}
                  {opt.predicted_outcome && opt.cost_estimate ? ' · ' : ''}
                  {opt.cost_estimate}
                </div>
              )}
            </article>
          ))}
      </div>

      {showOptionEditor && (
        <OptionEditor
          mode="create"
          onSave={async (opt) => {
            await onAddOption(opt);
            setShowOptionEditor(false);
          }}
          onClose={() => setShowOptionEditor(false)}
        />
      )}
    </section>
  );
}
