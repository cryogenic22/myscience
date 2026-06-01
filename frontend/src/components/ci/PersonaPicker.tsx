import { PERSONAS, usePersona, type Persona } from '../../hooks/usePersona';

/**
 * PB-UX01 — lightweight persona picker.
 *
 * Sets the viewer's persona (KC / SA / DM / EL), which DEFAULTS the experience
 * (landing stage, stage depth, available actions) — it does not restrict access.
 * Persisted to localStorage via usePersona. Deliberately small: a label + select,
 * not an admin permission UI.
 */
export default function PersonaPicker() {
  const [persona, setPersona] = usePersona();
  const current = PERSONAS.find((p) => p.id === persona);

  return (
    <label
      data-testid="persona-picker"
      title={current?.blurb}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--color-ink-3)',
      }}
    >
      <span style={{ letterSpacing: '.04em', textTransform: 'uppercase' }}>Viewing as</span>
      <select
        value={persona}
        onChange={(e) => setPersona(e.target.value as Persona)}
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          padding: '4px 8px',
          borderRadius: 'var(--radius-pill)',
          background: 'var(--color-surface-2)',
          color: 'var(--color-ink)',
          border: '1px solid var(--color-line)',
          cursor: 'pointer',
        }}
      >
        {PERSONAS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.id} · {p.label}
          </option>
        ))}
      </select>
    </label>
  );
}
