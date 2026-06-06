/**
 * DF — ForgePackPanel: the "I built this" payoff.
 *
 * As forge answers land, the live playbook grows. This panel shows the current
 * playbook's dimensions (the encoded expertise the SME is authoring by playing)
 * and its version, refreshing whenever a round is answered. When the round's
 * compare preview is available it reuses DecompositionMatrix to show the grown
 * playbook applied to two real entities (rows = dimensions, columns = entities).
 *
 * House style: design-token CSS variables + inline styles, no dynamic Tailwind
 * class names. Reuses DecompositionMatrix (PR #174) for the matrix preview.
 */
import { useEffect, useState } from 'react';
import { Layers, GitBranch } from 'lucide-react';
import {
  playbooksApi,
  type PlaybookDetail,
  type PlaybookDimension,
  type DecompositionMatrix as MatrixData,
} from '../../api';
import DecompositionMatrix from '../canvas/DecompositionMatrix';

interface Props {
  playbookId: string;
  /** Bump this to force a refetch (e.g. after a forge answer promotes). */
  refreshKey?: number;
  /** Optional live matrix preview (entities × dimensions) for the compare. */
  matrix?: MatrixData | null;
}

export default function ForgePackPanel({ playbookId, refreshKey = 0, matrix }: Props) {
  const [detail, setDetail] = useState<PlaybookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The playbook may not be DB-backed yet (no SME has promoted into it) — a 404
  // is the legitimate "not authored yet" state, not an error.
  const [notAuthored, setNotAuthored] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotAuthored(false);
    playbooksApi.get(playbookId)
      .then((d) => { if (!cancelled) { setDetail(d); setLoading(false); } })
      .catch((e: any) => {
        if (cancelled) return;
        const msg = String(e?.message ?? e);
        if (msg.startsWith('404')) { setNotAuthored(true); setDetail(null); }
        else setError(msg);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [playbookId, refreshKey]);

  const dims: PlaybookDimension[] = detail?.playbook?.dimensions ?? [];

  return (
    <div data-testid="forge-pack-panel">
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 10,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 7,
          fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--color-ink-3)',
        }}>
          <Layers size={13} /> Live playbook · {playbookId}
        </div>
        {detail?.meta?.version != null && (
          <span data-testid="forge-pack-version" style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-3)',
            background: 'var(--color-surface-3)', padding: '2px 9px', borderRadius: 'var(--radius-pill)',
          }}>
            <GitBranch size={11} /> v{detail.meta.version}
          </span>
        )}
      </div>

      {error && (
        <div data-testid="forge-pack-error" style={{
          color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 12.5, padding: 12,
        }}>{error}</div>
      )}

      {loading && (
        <div data-testid="forge-pack-loading" style={{
          fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-4)', padding: 12,
        }}>Loading playbook…</div>
      )}

      {!loading && notAuthored && (
        <div data-testid="forge-pack-empty" style={{
          fontSize: 12.5, color: 'var(--color-ink-3)', padding: '12px',
          background: 'var(--color-surface-2)', borderRadius: 10, lineHeight: 1.5,
        }}>
          No dimensions forged yet for this playbook. Play a round and reach SME
          consensus to promote the first dimension — it appears here live.
        </div>
      )}

      {!loading && !notAuthored && detail && (
        <>
          <div data-testid="forge-pack-dimensions" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {dims.length === 0 && (
              <div style={{ fontSize: 12.5, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
                Playbook has no dimensions yet.
              </div>
            )}
            {dims.map((d) => (
              <div
                key={d.key}
                data-testid={`forge-pack-dim-${d.key}`}
                style={{
                  padding: '9px 12px', borderRadius: 10,
                  background: 'var(--color-surface)', border: '1px solid var(--color-line)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-ink)' }}>{d.label}</span>
                  {d.required && (
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.06em',
                      textTransform: 'uppercase', color: 'var(--color-accent)',
                    }}>required</span>
                  )}
                </div>
                {d.routes.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 6 }}>
                    {d.routes.map((r) => (
                      <span key={r} style={{
                        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-ink-4)',
                        background: 'var(--color-surface-3)', padding: '1px 7px', borderRadius: 6,
                      }}>{r}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {matrix && matrix.dimensions.length > 0 && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.14em',
                textTransform: 'uppercase', color: 'var(--color-ink-4)', marginBottom: 8,
              }}>
                Compare preview — the playbook applied to real entities
              </div>
              <DecompositionMatrix matrix={matrix} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
