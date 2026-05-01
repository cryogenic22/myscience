import { useState } from 'react';
import { connectorsApi, type ConnectorDetail } from '../../api';

interface Props {
  detail: ConnectorDetail;
  onChanged: () => void;
}

function getRole(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('mz_auth_role');
}

export default function ConnectorPermissionsTab({ detail, onChanged }: Props) {
  const role = getRole();
  const isEnterprise = role === 'enterprise';
  const [enabled, setEnabled] = useState(detail.config.enabled);
  const [autoApprove, setAutoApprove] = useState(detail.config.auto_approve_runs);
  const [manualOnly, setManualOnly] = useState(detail.config.manual_only);
  const [notes, setNotes] = useState(detail.config.notes ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    enabled !== detail.config.enabled ||
    autoApprove !== detail.config.auto_approve_runs ||
    manualOnly !== detail.config.manual_only ||
    notes !== (detail.config.notes ?? '');

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await connectorsApi.updateConfig(detail.source_key, {
        enabled,
        auto_approve_runs: autoApprove,
        manual_only: manualOnly,
        notes: notes || null,
      });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      {!isEnterprise && (
        <div
          className="text-[12px]"
          style={{
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-line)',
            padding: '10px 14px',
            borderRadius: '6px',
            color: 'var(--color-ink-3)',
          }}
        >
          Read-only view — log in as <strong>enterprise</strong> to edit permissions.
        </div>
      )}

      <Toggle
        label="Enabled"
        description="When off, this connector is hidden from the scheduler and manual runs return 409."
        checked={enabled}
        onChange={setEnabled}
        disabled={!isEnterprise}
      />
      <Toggle
        label="Auto-approve runs"
        description="When on, uploader role can trigger manual runs. Otherwise enterprise required."
        checked={autoApprove}
        onChange={setAutoApprove}
        disabled={!isEnterprise}
      />
      <Toggle
        label="Manual only"
        description="When on, the scheduler skips this connector. Enterprise can still trigger manually."
        checked={manualOnly}
        onChange={setManualOnly}
        disabled={!isEnterprise}
      />

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
          Notes
        </div>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={!isEnterprise}
          rows={3}
          className="w-full text-[13px]"
          style={{
            border: '1px solid var(--color-line)',
            borderRadius: '6px',
            padding: '8px 10px',
            background: 'var(--color-surface)',
            color: 'var(--color-ink)',
          }}
        />
      </div>

      {error && (
        <div className="text-[12px]" style={{ color: '#B91C1C' }}>
          {error}
        </div>
      )}

      {isEnterprise && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            className="text-[13px] font-medium"
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              background: dirty && !saving ? 'var(--color-accent)' : 'var(--color-surface-2)',
              color: dirty && !saving ? 'white' : 'var(--color-ink-4)',
              cursor: dirty && !saving ? 'pointer' : 'not-allowed',
            }}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      )}
    </div>
  );
}

function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex-1">
        <div className="text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
          {label}
        </div>
        <div className="text-[12px] mt-0.5" style={{ color: 'var(--color-ink-4)' }}>
          {description}
        </div>
      </div>
      <button
        type="button"
        onClick={() => !disabled && onChange(!checked)}
        disabled={disabled}
        className="shrink-0"
        style={{
          width: '36px',
          height: '20px',
          borderRadius: '10px',
          background: checked ? 'var(--color-accent)' : 'var(--color-surface-2)',
          border: '1px solid var(--color-line)',
          position: 'relative',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
        }}
        aria-pressed={checked}
        aria-label={label}
      >
        <span
          style={{
            position: 'absolute',
            top: '1px',
            left: checked ? '17px' : '1px',
            width: '16px',
            height: '16px',
            borderRadius: '50%',
            background: 'white',
            transition: 'left 120ms ease',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </button>
    </div>
  );
}
