import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { warRoomApi, type MoveType, type WarRoom, type WarRoomMode } from '../../../api';
import CommentsPanel from './CommentsPanel';
import MoveSelector, { type MoveSelectorHandle } from './MoveSelector';
import MoveSuggestions from './MoveSuggestions';
import PayoffMatrix from './PayoffMatrix';
import RoomActionsMenu from './RoomActionsMenu';
import RoundHistory from './RoundHistory';
import WarRoomModePicker from './WarRoomModePicker';
import AutonomousPanel from './AutonomousPanel';
import { usePayoffMatrix } from '../../../hooks/usePayoffMatrix';

interface Props {
  roomId: string;
  onClose: () => void;
}

// Suggested move per signal KBQ tag — fed via ?signal_kbq= URL param
// when the room was opened from the Simulate button on a signal card.
const KBQ_TO_MOVE: Record<string, MoveType> = {
  clinical: 'trial_readout',
  m_and_a: 'acquisition',
  product: 'label_expansion',
  pricing_access: 'price_cut',
  regulatory: 'new_indication',
  strategic: 'segment_pivot',
  financial: 'price_cut',
  governance: 'segment_pivot',
};

export default function WarRoomView({ roomId, onClose }: Props) {
  const [params] = useSearchParams();
  const signalKbq = params.get('signal_kbq');
  const suggestedMove: MoveType =
    (signalKbq && KBQ_TO_MOVE[signalKbq]) || 'trial_readout';
  const selectorRef = useRef<MoveSelectorHandle>(null);
  const [room, setRoom] = useState<WarRoom | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [modeBusy, setModeBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await warRoomApi.detail(roomId);
      setRoom(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [roomId]);

  useEffect(() => { void reload(); }, [reload]);

  const mode: WarRoomMode = room?.mode ?? 'guided';

  const handleModeChange = async (next: WarRoomMode) => {
    if (!room || next === mode) return;
    const prev = room.mode ?? 'guided';
    setRoom({ ...room, mode: next });          // optimistic
    setModeBusy(true);
    setError(null);
    try {
      await warRoomApi.setMode(roomId, next);
    } catch (e) {
      setRoom((r) => (r ? { ...r, mode: prev } : r));  // revert
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setModeBusy(false);
    }
  };

  const handleSubmit = async (move_type: MoveType, payload: Record<string, string>) => {
    setBusy(true);
    setError(null);
    try {
      await warRoomApi.submitRound(roomId, {
        move_type,
        move_payload: payload,
        player_company_name: room?.primary_entity_name ?? 'Player',
      });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !room) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-[13px]"
        style={{ color: 'var(--color-ink-4)' }}
      >
        Loading war room…
      </div>
    );
  }

  if (!room) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-[13px]"
        style={{ color: '#B91C1C' }}
      >
        {error || 'War room not found.'}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '20px 28px' }}>
      {/* Header */}
      <div className="mb-5">
        <button
          type="button"
          onClick={onClose}
          className="text-[12px] mb-3 inline-flex items-center gap-1"
          style={{ color: 'var(--color-ink-4)' }}
        >
          <ChevronLeft size={13} />
          Back to CI
        </button>
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              background: 'var(--color-surface-2)',
              color: 'var(--color-ink-3)',
              letterSpacing: '0.06em',
            }}
          >
            {room.game_phase}
          </span>
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              background: room.status === 'active' ? '#DCFCE7' : 'var(--color-surface-2)',
              color: room.status === 'active' ? '#15803D' : 'var(--color-ink-4)',
              letterSpacing: '0.06em',
            }}
          >
            {room.status}
          </span>
          {room.archived_at && (
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                background: '#F3E8FF',
                color: '#6D28D9',
                letterSpacing: '0.06em',
              }}
              title={`Archived ${new Date(room.archived_at).toLocaleDateString()}`}
            >
              archived
            </span>
          )}
          <div className="ml-auto">
            <RoomActionsMenu
              room={room}
              onChange={(updated) => setRoom(updated)}
              onClosed={onClose}
            />
          </div>
        </div>
        <h1
          className="font-display text-[22px]"
          style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
        >
          {room.title}
        </h1>
        {room.scenario_question && (
          <div
            className="text-[13px] mt-2"
            style={{ color: 'var(--color-ink-3)' }}
          >
            {room.scenario_question}
          </div>
        )}
        {room.primary_entity_name && (
          <div className="text-[12px] mt-2" style={{ color: 'var(--color-ink-4)' }}>
            Subject: <span style={{ color: 'var(--color-ink-2)' }}>{room.primary_entity_name}</span>
          </div>
        )}
      </div>

      {/* IX04a — mode picker over the shared scenario state. */}
      <WarRoomModePicker mode={mode} onModeChange={handleModeChange} busy={modeBusy} />

      {/* Guided — Strategist's payoff matrix + suggestions + move composer.
          The backend gates round submission to Guided mode, so the composer
          only renders here. Loop #10 consolidated these three siblings into one
          panel; Loop #11 dropped the border for a background-elevation tier. */}
      {mode === 'guided' && (
        <section
          aria-label="Strategy"
          className="mb-8"
          style={{
            padding: '24px',
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-panel)',
          }}
        >
          <header
            className="flex items-baseline justify-between"
            style={{ marginBottom: '16px' }}
          >
            <h2
              className="mz-text-xs uppercase font-medium"
              style={{ color: 'var(--color-ink-3)', letterSpacing: '0.08em' }}
            >
              Strategy
            </h2>
            <span className="mz-text-xs" style={{ color: 'var(--color-ink-4)' }}>
              Strategist · payoff matrix · move
            </span>
          </header>

          <PayoffMatrixSection roomId={roomId} />
          <MoveSuggestions
            roomId={roomId}
            signalContext={signalKbq ? { kbq_tags: [signalKbq] } : undefined}
            onPick={(move_type, payload) => {
              selectorRef.current?.applySuggestion(move_type, payload);
            }}
          />
          <div style={{ marginTop: '16px' }}>
            <MoveSelector
              ref={selectorRef}
              onSubmit={handleSubmit}
              busy={busy}
              initialMoveType={suggestedMove}
              roomId={roomId}
            />
          </div>
        </section>
      )}

      {/* Game-theoretic — the payoff matrix is the surface; the 3×3 NPV-pair
          Nash solver arrives in L2 (PB-H12). */}
      {mode === 'game_theoretic' && (
        <section
          aria-label="Game-theoretic"
          className="mb-8"
          style={{ padding: '24px', background: 'var(--color-surface-2)', borderRadius: 'var(--radius-panel)' }}
        >
          <header className="flex items-baseline justify-between" style={{ marginBottom: '16px' }}>
            <h2 className="mz-text-xs uppercase font-medium" style={{ color: 'var(--color-ink-3)', letterSpacing: '0.08em' }}>
              Game-theoretic
            </h2>
            <span className="mz-text-xs" style={{ color: 'var(--color-ink-4)' }}>3×3 payoff · Nash equilibrium</span>
          </header>
          <PayoffMatrixSection
            roomId={roomId}
            ourMoves={GT_OUR_MOVES}
            adversaryStates={GT_ADVERSARY_MOVES}
          />
        </section>
      )}

      {/* Autonomous — agents play every team and narrate; the human observes
          (PB-H13). Reactions are DB-grounded server-side. */}
      {mode === 'autonomous' && (
        <section
          aria-label="Autonomous"
          className="mb-8"
          style={{ padding: '24px', background: 'var(--color-surface-2)', borderRadius: 'var(--radius-panel)' }}
        >
          <header className="flex items-baseline justify-between" style={{ marginBottom: '16px' }}>
            <h2 className="mz-text-xs uppercase font-medium" style={{ color: 'var(--color-ink-3)', letterSpacing: '0.08em' }}>
              Autonomous
            </h2>
            <span className="mz-text-xs" style={{ color: 'var(--color-ink-4)' }}>agents play · narrated</span>
          </header>
          <AutonomousPanel roomId={roomId} />
        </section>
      )}

      {error && (
        <div
          className="text-[12px] mb-4"
          style={{
            padding: '10px 14px',
            background: '#FEF2F2',
            color: '#B91C1C',
            borderRadius: '6px',
          }}
        >
          {error}
        </div>
      )}

      {/* Round history */}
      <div className="mb-6">
        <div
          className="text-[10px] uppercase font-medium mb-3"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Simulation history ({room.rounds?.length ?? 0} round{room.rounds?.length === 1 ? '' : 's'})
        </div>
        <RoundHistory rounds={room.rounds ?? []} />
      </div>

      {/* Phase B — Comments */}
      <div>
        <div
          className="text-[10px] uppercase font-medium mb-3"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Discussion
        </div>
        <CommentsPanel roomId={roomId} ownerUserId={room.owner_user_id} />
      </div>
    </div>
  );
}

/**
 * PB-501 — Payoff matrix panel.
 *
 * Renders the 2×2 matrix above the existing move-selector flow.
 * Today the data is mocked via `usePayoffMatrix`; when BE-8 ships
 * the hook swaps to a real `POST /war-rooms/{id}/payoff-matrix`
 * call without changing this component.
 */
// Game-theoretic mode plays a 3×3 of strategic postures so the Nash
// (security) equilibrium has room to differ from the EV pick. Guided mode
// keeps the hook's 2×2 default.
const GT_OUR_MOVES = ['launch_q3', 'wait_q4', 'partner'];
const GT_ADVERSARY_MOVES = ['defend', 'cede', 'escalate'];

function PayoffMatrixSection({
  roomId,
  ourMoves,
  adversaryStates,
}: {
  roomId: string;
  ourMoves?: string[];
  adversaryStates?: string[];
}) {
  const { data, error, isLoading } = usePayoffMatrix(roomId, { ourMoves, adversaryStates });
  if (isLoading) {
    return (
      <div
        className="mz-text-sm"
        style={{ color: 'var(--color-ink-4)', marginBottom: '16px' }}
      >
        Loading payoff matrix…
      </div>
    );
  }
  if (error || !data) {
    return null;
  }
  return <PayoffMatrix matrix={data} />;
}
