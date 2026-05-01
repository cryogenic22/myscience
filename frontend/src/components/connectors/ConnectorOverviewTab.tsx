import type { ConnectorDetail } from '../../api';

export default function ConnectorOverviewTab({ detail }: { detail: ConnectorDetail }) {
  return (
    <div className="space-y-5">
      {detail.description && (
        <Field label="About">
          <p className="text-[14px] leading-relaxed" style={{ color: 'var(--color-ink-2)' }}>
            {detail.description}
          </p>
        </Field>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Field label="Schedule">
          <span className="text-[13px]" style={{ color: 'var(--color-ink)' }}>
            {detail.schedule}
          </span>
        </Field>
        <Field label="Last successful run">
          <span className="text-[13px]" style={{ color: 'var(--color-ink)' }}>
            {detail.last_run?.completed_at
              ? new Date(detail.last_run.completed_at).toLocaleString()
              : 'Never'}
          </span>
        </Field>
        {detail.license && (
          <Field label="License">
            {detail.license_url ? (
              <a
                href={detail.license_url}
                target="_blank"
                rel="noreferrer"
                className="text-[13px] underline"
                style={{ color: 'var(--color-accent)' }}
              >
                {detail.license}
              </a>
            ) : (
              <span className="text-[13px]" style={{ color: 'var(--color-ink)' }}>
                {detail.license}
              </span>
            )}
          </Field>
        )}
        {detail.api_base_url && (
          <Field label="API endpoint">
            <a
              href={detail.api_base_url}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] font-mono break-all"
              style={{ color: 'var(--color-accent)' }}
            >
              {detail.api_base_url}
            </a>
          </Field>
        )}
      </div>

      {detail.config.notes && (
        <Field label="Notes">
          <p className="text-[13px] italic" style={{ color: 'var(--color-ink-3)' }}>
            {detail.config.notes}
          </p>
        </Field>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="text-[10px] uppercase tracking-wider"
        style={{
          color: 'var(--color-ink-4)',
          marginBottom: '6px',
          letterSpacing: '0.06em',
          fontWeight: 500,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
