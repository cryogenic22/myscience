import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft } from 'lucide-react';
import { warRoomApi, type MoveType, type WarRoom } from '../../../api';
import MoveSelector from './MoveSelector';
import RoundHistory from './RoundHistory';

interface Props {
  roomId: string;
  onClose: () => void;
}

const KBQ_TO_MOVE: Record<string, MoveType> = {
  clinical: 'trial_readout',
  m_and_a: 'acquisition',
  product: 'label_expansion',
  pricing_access: 'price_cut',
  regulatory: 'new_indication',
  strategic: 'segment_pivot',
};

export default function WarRoomView({ roomId, onClose }: Props) {
  const [room, setRoom] = useState<WarRoom | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
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

  // Suggested move from source signal's KBQ if present in URL state (later)
  const suggested: MoveType = 'trial_readout';

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

      {/* Move selector */}
      <div className="mb-6">
        <MoveSelector
          onSubmit={handleSubmit}
          busy={busy}
          initialMoveType={suggested}
        />
      </div>

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
      <div>
        <div
          className="text-[10px] uppercase font-medium mb-3"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Simulation history ({room.rounds?.length ?? 0} round{room.rounds?.length === 1 ? '' : 's'})
        </div>
        <RoundHistory rounds={room.rounds ?? []} />
      </div>
    </div>
  );
}
