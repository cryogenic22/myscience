import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useDossier } from '../hooks/useDossier';
import type { DossierEntityType, DossierEvidence } from '../types/dossier';
import { PRODUCT_NAME } from '../brand';
import { ThemeToggle } from '../components/primitives/ThemeToggle';

/**
 * Entity dossier — three-column layout (identity rail · synthesis
 * main · evidence pile) for `/dossier/:entityType/:slug`. Wired to
 * the BE-6 composer (`GET /dossier/{type}/{slug}`) via `useDossier`.
 *
 * Loop #11 — borderless surfaces via background-tier elevation
 * (Spotify/Oura model). Identity + evidence rails sit on
 * `--color-surface-2`; synthesis main on `--color-surface`. No
 * vertical 1px rules between columns.
 */

const KNOWN_TYPES: DossierEntityType[] = ['drug', 'company', 'mechanism', 'trial', 'therapeutic_area'];

function isKnownType(s: string | undefined): s is DossierEntityType {
  return typeof s === 'string' && (KNOWN_TYPES as string[]).includes(s);
}

const TIER_LABEL: Record<DossierEvidence['tier'], string> = {
  T1: 'T1 · authoritative',
  T2: 'T2 · disclosure',
  T3: 'T3 · scientific',
  T4: 'T4 · licensed',
};

export default function DossierPage() {
  const { entityType: rawType, slug } = useParams<{ entityType: string; slug: string }>();
  const entityType = isKnownType(rawType) ? rawType : undefined;
  const { data, error, isLoading } = useDossier(entityType, slug);

  if (!entityType) {
    return (
      <ScaffoldShell>
        <CenteredMessage
          heading="Unknown entity type"
          body={`"${rawType}" is not a dossier entity type. Expected one of: ${KNOWN_TYPES.join(', ')}.`}
        />
      </ScaffoldShell>
    );
  }

  if (isLoading) {
    return (
      <ScaffoldShell>
        <CenteredMessage heading="Loading dossier…" body={`${entityType} · ${slug}`} />
      </ScaffoldShell>
    );
  }

  if (error) {
    const status = (error as Error & { status?: number }).status;
    if (status === 404) {
      return (
        <ScaffoldShell>
          <CenteredMessage
            heading={`No dossier for "${slug}"`}
            body={`We did not find a ${entityType} with that identifier. It may have been merged, renamed, or never seeded.`}
          />
        </ScaffoldShell>
      );
    }
    return (
      <ScaffoldShell>
        <CenteredMessage heading="Could not load dossier" body={error.message} />
      </ScaffoldShell>
    );
  }

  if (!data) {
    return (
      <ScaffoldShell>
        <CenteredMessage heading="Dossier unavailable" body="The composer returned no payload." />
      </ScaffoldShell>
    );
  }

  const { entity, synthesis, evidence } = data;
  const visibleEvidence = evidence.slice(0, 3);
  const hiddenCount = Math.max(0, evidence.length - visibleEvidence.length);

  return (
    <ScaffoldShell>
      {/* Entity title bar — sits flush on the page background, no border. */}
      <div
        className="flex items-baseline gap-4 flex-wrap"
        style={{ padding: '32px 32px 24px 32px' }}
      >
        <h1 className="font-display mz-text-display" style={{ color: 'var(--color-ink)' }}>
          {entity.canonical_name}
        </h1>
        <span
          className="mz-text-xs font-medium uppercase tracking-wide"
          style={{
            padding: '3px 10px',
            borderRadius: 'var(--radius-pill)',
            background: 'var(--color-surface-2)',
            color: 'var(--color-ink-3)',
            letterSpacing: '0.08em',
          }}
        >
          {entity.type}
        </span>
        <span className="mz-text-sm ml-auto" style={{ color: 'var(--color-ink-4)' }}>
          Last updated {new Date(entity.updated_at).toLocaleDateString()}
        </span>
      </div>

      <div className="flex-1 grid overflow-hidden" style={{ gridTemplateColumns: '260px 1fr 320px', gap: '0' }}>
        {/* Identity rail — tinted surface, no vertical divider. */}
        <aside
          className="overflow-y-auto"
          style={{
            padding: '24px',
            background: 'var(--color-surface-2)',
          }}
          aria-label="Identity"
        >
          {entity.aliases.length > 0 && (
            <IdentityBlock title="Aliases">
              <ul className="space-y-1.5">
                {entity.aliases.map((a) => (
                  <li key={a} className="mz-text-sm" style={{ color: 'var(--color-ink-2)' }}>{a}</li>
                ))}
              </ul>
            </IdentityBlock>
          )}
          {Object.keys(entity.external_ids).length > 0 && (
            <IdentityBlock title="External IDs">
              <dl className="space-y-1.5">
                {Object.entries(entity.external_ids).map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-3">
                    <dt className="mz-text-xs uppercase" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}>{k}</dt>
                    <dd className="mz-text-sm font-mono" style={{ color: 'var(--color-ink-2)' }}>{v}</dd>
                  </div>
                ))}
              </dl>
            </IdentityBlock>
          )}
          {Object.keys(entity.primary_attributes).length > 0 && (
            <IdentityBlock title="Attributes">
              <dl className="space-y-1.5">
                {Object.entries(entity.primary_attributes).map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-3">
                    <dt className="mz-text-xs uppercase" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}>{k.replace(/_/g, ' ')}</dt>
                    <dd className="mz-text-sm" style={{ color: 'var(--color-ink-2)' }}>{v ?? '—'}</dd>
                  </div>
                ))}
              </dl>
            </IdentityBlock>
          )}
        </aside>

        {/* Synthesis main — clean surface. Generous left/right padding so
            the long paragraph has comfortable measure (~70ch). */}
        <main
          className="overflow-y-auto"
          style={{ padding: '32px 48px', background: 'var(--color-surface)' }}
          aria-label="Synthesis"
        >
          {synthesis ? (
            <p
              className="font-display"
              style={{
                color: 'var(--color-ink)',
                fontSize: 'var(--text-lg)',
                lineHeight: '1.6',
                maxWidth: '70ch',
              }}
            >
              {synthesis.summary}
            </p>
          ) : (
            <p className="mz-text-sm italic" style={{ color: 'var(--color-ink-4)' }}>
              Synthesis pending — the LLM has not yet composed a narrative for this entity.
            </p>
          )}
        </main>

        {/* Evidence pile — tinted surface, no vertical divider. */}
        <aside
          className="overflow-y-auto"
          style={{
            padding: '24px',
            background: 'var(--color-surface-2)',
          }}
          aria-label="Evidence"
        >
          <h2
            className="mz-text-xs uppercase font-medium"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em', marginBottom: '16px' }}
          >
            Evidence
          </h2>
          {visibleEvidence.length === 0 ? (
            <p className="mz-text-sm" style={{ color: 'var(--color-ink-4)' }}>No evidence on file yet.</p>
          ) : (
            <ul className="space-y-3">
              {visibleEvidence.map((ev) => (
                <li
                  key={ev.id}
                  className="mz-elevated"
                  style={{
                    padding: '12px 14px',
                    background: 'var(--color-surface)',
                    borderRadius: 'var(--radius-card)',
                  }}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="mz-text-sm font-medium" style={{ color: 'var(--color-ink-2)' }}>
                      {ev.source_name}
                    </span>
                    <span className="mz-text-xs uppercase" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}>
                      {TIER_LABEL[ev.tier]}
                    </span>
                  </div>
                  <div className="mz-text-xs" style={{ color: 'var(--color-ink-4)', marginTop: '2px' }}>
                    {new Date(ev.published_at).toLocaleDateString()}
                  </div>
                  <p className="mz-text-sm" style={{ color: 'var(--color-ink-3)', marginTop: '6px', lineHeight: '1.55' }}>
                    {ev.snippet}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {hiddenCount > 0 && (
            <button
              type="button"
              className="mz-text-sm underline"
              style={{ color: 'var(--color-accent)', cursor: 'pointer', marginTop: '16px' }}
            >
              +{hiddenCount} more
            </button>
          )}
        </aside>
      </div>
    </ScaffoldShell>
  );
}

function ScaffoldShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  return (
    <div
      className="flex flex-col h-screen"
      style={{ background: 'var(--color-bg)', color: 'var(--color-ink)' }}
    >
      <header
        className="shrink-0 flex items-center gap-4"
        style={{
          height: '56px',
          padding: '0 24px',
          borderBottom: '1px solid var(--color-divider)',
          background: 'var(--color-surface)',
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/ci')}
          className="btn-icon"
          aria-label="Back"
          title="Back to cockpit"
        >
          <ArrowLeft size={15} />
        </button>
        <span
          className="font-display"
          style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-md)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>
        <div className="h-4 w-px" style={{ background: 'var(--color-divider)' }} />
        <span className="font-display" style={{ color: 'var(--color-ink)', fontSize: 'var(--text-md)' }}>
          Dossier
        </span>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>
      {children}
    </div>
  );
}

function CenteredMessage({ heading, body }: { heading: string; body: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3" style={{ padding: '48px' }}>
      <h2 className="font-display mz-text-xl" style={{ color: 'var(--color-ink)' }}>{heading}</h2>
      <p className="mz-text-sm text-center" style={{ color: 'var(--color-ink-3)', maxWidth: '480px', lineHeight: '1.55' }}>{body}</p>
    </div>
  );
}

function IdentityBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: '24px' }}>
      <h3
        className="mz-text-xs uppercase font-medium"
        style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em', marginBottom: '10px' }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}
