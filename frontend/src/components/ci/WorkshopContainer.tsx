/**
 * UX-Workshop — WorkshopContainer.
 *
 * The final engagement stage: turn a scenario into a played war game. Bridges
 * the engagement's scenarios (PB-H09) to the existing War Room infra — launch a
 * room seeded from a scenario (its trigger becomes the scenario_question, the
 * focal asset becomes the primary entity), then play it inline. Existing rooms
 * for the asset are listed so a workshop can be resumed.
 *
 * States: loading → ready (launch list + existing rooms) → error.
 * When a room is active, WarRoomView renders inline (self-contained).
 */
import { useCallback, useEffect, useState } from 'react';
import { scenariosApi, warRoomApi, type WarRoom, type EngagementDTO } from '../../api';
import { type Scenario } from '../../pages/ScenariosPage';
import WarRoomView from './war/WarRoomView';

interface Props {
  engagement: EngagementDTO;
  onMarkComplete?: () => void;
}

function assetParts(asset: string): { type: string; name: string } {
  const [type, ...rest] = (asset || '').split(':');
  const name = rest.join(':').trim();
  return name ? { type: type.trim(), name } : { type: 'drug', name: asset };
}

export default function WorkshopContainer({ engagement, onMarkComplete }: Props) {
  const eid = engagement.id;
  const { type: assetType, name: assetName } = assetParts(engagement.asset);

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [rooms, setRooms] = useState<WarRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const [activeRoom, setActiveRoom] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      scenariosApi.get(eid).then((r) => r.scenarios).catch(() => [] as Scenario[]),
      warRoomApi.list({ q: assetName }).then((r) => r.war_rooms).catch(() => [] as WarRoom[]),
    ])
      .then(([scs, rms]) => { if (!cancelled) { setScenarios(scs); setRooms(rms); } })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid, assetName]);

  useEffect(() => load(), [load]);

  const launch = async (s: Scenario) => {
    setLaunching(s.id);
    setError(null);
    try {
      const room = await warRoomApi.create({
        title: s.name,
        scenario_question: s.trigger.event,
        primary_entity_type: assetType,
        primary_entity_id: assetName,
        primary_entity_name: assetName,
      });
      setActiveRoom(room.id);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setLaunching(null);
    }
  };

  // Active room → play it inline.
  if (activeRoom) {
    return (
      <div data-testid="workshop-room">
        <WarRoomView roomId={activeRoom} onClose={() => { setActiveRoom(null); load(); }} />
      </div>
    );
  }

  if (loading) {
    return <Centered testId="workshop-loading" tone="var(--color-ink-3)">Loading workshop…</Centered>;
  }

  if (error) {
    return (
      <div data-testid="workshop-error" style={{ padding: 'var(--space-7)' }}>
        <ErrorLine>{error}</ErrorLine>
        <button onClick={load} style={{ marginTop: 12, padding: '8px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, borderRadius: 'var(--radius-pill)', border: 'none', cursor: 'pointer', background: 'var(--color-surface-2)', color: 'var(--color-ink)' }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <main
      data-testid="workshop-ready"
      role="main"
      aria-label="Workshop"
      style={{
        display: 'flex', flexDirection: 'column', gap: 22,
        padding: '24px 28px 40px', background: 'var(--color-bg)',
        color: 'var(--color-ink-2)', fontFamily: 'var(--font-body)', minHeight: '100%',
      }}
    >
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: 18, borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
          Stage 07 · War Room &amp; Decisions
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 400, color: 'var(--color-ink)', letterSpacing: '-0.014em', margin: 0 }}>
            Play the scenarios.
          </h1>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--color-ink-3)' }}>
            {engagement.name} · {engagement.asset}
          </span>
        </div>
      </header>

      {/* Launch from a scenario */}
      <section>
        <SectionLabel>Launch a war game from a scenario</SectionLabel>
        {scenarios.length === 0 ? (
          <Empty>No scenarios yet — derive them in the Scenarios stage first.</Empty>
        ) : (
          <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {scenarios.map((s) => {
              const blocked = (s.blockedByGaps?.length ?? 0) > 0;
              return (
                <li key={s.id} data-scenario-id={s.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', background: 'var(--color-surface)', border: '1px solid var(--color-line)', borderLeft: '3px solid var(--color-accent)' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 500, color: 'var(--color-ink)' }}>{s.name}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--color-ink-3)', lineHeight: 1.4 }}>{s.trigger.event}</div>
                  </div>
                  <button
                    type="button"
                    data-testid={`workshop-launch-${s.id}`}
                    disabled={blocked || launching === s.id}
                    onClick={() => !blocked && launch(s)}
                    title={blocked ? 'Resolve blocking gaps first' : 'Launch a war room'}
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.12em',
                      textTransform: 'uppercase', padding: '8px 14px', fontWeight: 600,
                      background: blocked ? 'var(--color-surface-2)' : 'var(--color-accent)',
                      color: blocked ? 'var(--color-ink-3)' : 'var(--color-surface)',
                      border: `1px solid ${blocked ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
                      cursor: blocked ? 'not-allowed' : (launching === s.id ? 'wait' : 'pointer'),
                    }}
                  >
                    {launching === s.id ? 'Launching…' : 'Play in War Room →'}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Resume an existing room */}
      {rooms.length > 0 && (
        <section>
          <SectionLabel>Resume a war room</SectionLabel>
          <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rooms.map((rm) => (
              <li key={rm.id}>
                <button
                  type="button"
                  data-testid={`workshop-resume-${rm.id}`}
                  onClick={() => setActiveRoom(rm.id)}
                  style={{
                    width: '100%', textAlign: 'left', cursor: 'pointer',
                    padding: '10px 14px', background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-line)', display: 'flex', gap: 10, alignItems: 'baseline',
                  }}
                >
                  <span style={{ fontSize: 14, color: 'var(--color-ink)', fontWeight: 500 }}>{rm.title}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-ink-3)' }}>{rm.status} · {rm.game_phase}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, paddingTop: 16, borderTop: '1px solid var(--color-divider)' }}>
        <button
          type="button"
          aria-label="Mark stage complete"
          onClick={() => onMarkComplete?.()}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.16em',
            textTransform: 'uppercase', padding: '8px 16px',
            background: 'var(--color-accent)', color: 'var(--color-surface)',
            border: '1px solid var(--color-accent)', cursor: 'pointer', fontWeight: 600,
          }}
        >
          Mark engagement complete →
        </button>
      </footer>
    </main>
  );
}

// ── atoms ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 12 }}>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: 20, border: '1px dashed var(--color-line-2)', color: 'var(--color-ink-3)', fontStyle: 'italic', textAlign: 'center' }}>
      {children}
    </div>
  );
}

function Centered({ children, testId, tone }: { children: React.ReactNode; testId: string; tone: string }) {
  return (
    <div data-testid={testId} style={{ padding: 'var(--space-7)', color: tone, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      {children}
    </div>
  );
}

function ErrorLine({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: '0 0 4px', color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
      {children}
    </p>
  );
}
