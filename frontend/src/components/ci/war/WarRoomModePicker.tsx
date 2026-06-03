/**
 * IX04a — War Game mode picker.
 *
 * A three-mode tablist (Guided / Autonomous / Game-theoretic) over one shared
 * war-room scenario state. Harvested from the unused F11 `WarRoomPage` design
 * artifact and wired into the live `WarRoomView`. Backed by
 * `PATCH /war-rooms/{id}/mode` (services/scenario_state.py); the move composer
 * is Guided-only (the backend gates `submitRound` to guided), so each mode
 * surfaces a different body in WarRoomView.
 */
import type { WarRoomMode } from '../../../api';

const MODES: WarRoomMode[] = ['guided', 'autonomous', 'game_theoretic'];

const LABEL: Record<WarRoomMode, string> = {
  guided: 'Guided',
  autonomous: 'Autonomous',
  game_theoretic: 'Game-theoretic',
};

interface Props {
  mode: WarRoomMode;
  onModeChange: (m: WarRoomMode) => void;
  /** Disable switching while a mode transition is in flight. */
  busy?: boolean;
}

export default function WarRoomModePicker({ mode, onModeChange, busy = false }: Props) {
  return (
    <div
      role="tablist"
      aria-label="War Game mode"
      style={{
        display: 'flex',
        gap: 0,
        borderBottom: '1px solid var(--color-line)',
        marginBottom: 20,
      }}
    >
      {MODES.map((m) => {
        const active = m === mode;
        return (
          <button
            key={m}
            type="button"
            role="tab"
            data-mode={m}
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            disabled={busy}
            onClick={() => { if (!active && !busy) onModeChange(m); }}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              padding: '12px 16px',
              background: 'transparent',
              color: active ? 'var(--color-accent)' : 'var(--color-ink-3)',
              border: 'none',
              borderBottom: `2px solid ${active ? 'var(--color-accent)' : 'transparent'}`,
              cursor: busy ? 'default' : 'pointer',
              fontWeight: active ? 600 : 500,
              opacity: busy && !active ? 0.5 : 1,
            }}
          >
            {LABEL[m]}
          </button>
        );
      })}
    </div>
  );
}
