import { useState } from 'react';
import { connectorsApi, type ConnectorDetail, type HealthCheckResponse } from '../../api';

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

const STATUS_COLOR: Record<string, string> = {
  SUCCESS: '#15803D',
  PARTIAL: '#A16207',
  FAILED: '#B91C1C',
  RUNNING: '#1D4ED8',
};

export default function ConnectorHealthTab({ detail }: { detail: ConnectorDetail }) {
  const [result, setResult] = useState<HealthCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const authed = hasToken();

  const ping = async () => {
    setChecking(true);
    setError(null);
    setResult(null);
    try {
      const r = await connectorsApi.healthCheck(detail.source_key);
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between" style={{ marginBottom: '12px' }}>
          <div className="text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
            Live health check
          </div>
          <button
            type="button"
            onClick={ping}
            disabled={!authed || checking}
            className="text-[12px] font-medium"
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              background: authed && !checking ? 'var(--color-accent)' : 'var(--color-surface-2)',
              color: authed && !checking ? 'white' : 'var(--color-ink-4)',
              cursor: authed && !checking ? 'pointer' : 'not-allowed',
            }}
            title={!authed ? 'Log in as uploader or higher to run health checks' : ''}
          >
            {checking ? 'Checking…' : 'Run health check'}
          </button>
        </div>

        {!authed && (
          <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
            Log in as <strong>uploader</strong> or higher to ping this source.
          </div>
        )}

        {result && (
          <div
            style={{
              border: '1px solid var(--color-line)',
              borderRadius: '6px',
              padding: '12px 14px',
              background: result.healthy ? '#F0FDF4' : '#FEF2F2',
              marginTop: '8px',
            }}
          >
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: result.healthy ? '#22C55E' : '#EF4444' }}
              />
              <span
                className="text-[13px] font-medium"
                style={{ color: result.healthy ? '#15803D' : '#B91C1C' }}
              >
                {result.healthy ? 'Healthy' : 'Unhealthy'}
              </span>
              {result.response_time_ms != null && (
                <span className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
                  {result.response_time_ms.toFixed(0)} ms
                </span>
              )}
            </div>
            {result.message && (
              <div
                className="text-[12px] mt-1"
                style={{ color: 'var(--color-ink-3)' }}
              >
                {result.message}
              </div>
            )}
          </div>
        )}

        {error && (
          <div
            className="text-[12px] mt-2"
            style={{ color: '#B91C1C' }}
          >
            {error}
          </div>
        )}
      </div>

      <div>
        <div
          className="text-[10px] uppercase tracking-wider"
          style={{
            color: 'var(--color-ink-4)',
            marginBottom: '8px',
            letterSpacing: '0.06em',
            fontWeight: 500,
          }}
        >
          Recent runs
        </div>
        {detail.recent_runs.length === 0 ? (
          <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
            No runs recorded yet.
          </div>
        ) : (
          <div
            style={{
              border: '1px solid var(--color-line)',
              borderRadius: '6px',
              overflow: 'hidden',
            }}
          >
            {detail.recent_runs.map((run, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-[12px]"
                style={{
                  padding: '8px 14px',
                  borderBottom:
                    idx < detail.recent_runs.length - 1
                      ? '1px solid var(--color-line)'
                      : 'none',
                  color: 'var(--color-ink-3)',
                }}
              >
                <div className="flex items-center gap-3">
                  <span
                    className="text-[10px] font-medium uppercase"
                    style={{
                      color: STATUS_COLOR[run.status] ?? 'var(--color-ink-4)',
                      width: '60px',
                    }}
                  >
                    {run.status}
                  </span>
                  <span>
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </span>
                </div>
                <span style={{ color: 'var(--color-ink-4)' }}>
                  {run.records_inserted != null
                    ? `${run.records_inserted.toLocaleString()} records`
                    : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
