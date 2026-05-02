import { useState } from 'react';
import { MOVE_TYPE_META, type MoveType } from '../../../api';

interface Props {
  onSubmit: (move_type: MoveType, payload: Record<string, string>) => void;
  busy: boolean;
  initialMoveType?: MoveType;
}

const MOVE_KEYS = Object.keys(MOVE_TYPE_META) as MoveType[];

export default function MoveSelector({ onSubmit, busy, initialMoveType = 'trial_readout' }: Props) {
  const [moveType, setMoveType] = useState<MoveType>(initialMoveType);
  const [payload, setPayload] = useState<Record<string, string>>({});

  const meta = MOVE_TYPE_META[moveType];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(moveType, payload);
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        border: '1px solid var(--color-line)',
        borderRadius: '8px',
        padding: '16px 18px',
        background: 'var(--color-surface)',
      }}
    >
      <div
        className="text-[10px] uppercase font-medium mb-3"
        style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
      >
        Submit a move
      </div>

      {/* Move type chips */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {MOVE_KEYS.map((k) => {
          const m = MOVE_TYPE_META[k];
          const active = k === moveType;
          return (
            <button
              key={k}
              type="button"
              onClick={() => { setMoveType(k); setPayload({}); }}
              className="text-[12px] flex items-center gap-1.5"
              style={{
                padding: '5px 10px',
                borderRadius: '6px',
                border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-line)'}`,
                background: active ? 'var(--color-accent)' : 'transparent',
                color: active ? 'white' : 'var(--color-ink-2)',
              }}
            >
              <span>{m.icon}</span>
              <span>{m.label}</span>
            </button>
          );
        })}
      </div>

      <div
        className="text-[12px] mb-3"
        style={{ color: 'var(--color-ink-3)', fontStyle: 'italic' }}
      >
        {meta.desc}
      </div>

      {/* Dynamic payload fields */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        {meta.fields.map((field) => (
          <input
            key={field}
            value={payload[field] ?? ''}
            onChange={(e) => setPayload({ ...payload, [field]: e.target.value })}
            placeholder={field.replace(/_/g, ' ')}
            className="text-[12px]"
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink)',
            }}
          />
        ))}
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={busy}
          className="text-[13px] font-medium"
          style={{
            padding: '7px 16px',
            borderRadius: '6px',
            background: busy ? 'var(--color-surface-2)' : 'var(--color-accent)',
            color: busy ? 'var(--color-ink-4)' : 'white',
            border: 'none',
            cursor: busy ? 'not-allowed' : 'pointer',
          }}
        >
          {busy ? 'Modeling reactions…' : 'Run simulation'}
        </button>
      </div>
    </form>
  );
}
