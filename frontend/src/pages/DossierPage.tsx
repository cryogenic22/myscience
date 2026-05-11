import { useParams } from 'react-router-dom';
import { useDossier } from '../hooks/useDossier';
import type { DossierEntityType, DossierEvidence } from '../types/dossier';

/**
 * PB-301 — Entity dossier scaffold.
 *
 * Three-column layout (`identity rail · synthesis main · evidence pile`)
 * for `/dossier/:entityType/:slug`. Backend composer ships via BE-6
 * (PR #57); for now `useDossier` returns a mock fixture so the layout
 * can be reviewed end-to-end.
 *
 * When BE-6 lands:
 * 1. Replace the body of `fetchDossier` in `src/hooks/useDossier.ts`
 *    with a real `fetch(${BASE}/dossier/${type}/${slug})` call.
 * 2. Drop the `is_mock` field from the type + remove the placeholder
 *    notice rendered in this file (search for `data.is_mock`).
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
      {/* Mock-data notice — drop when BE-6 ships. */}
      {data.is_mock && (
        <div
          role="status"
          className="text-[11px]"
          style={{
            padding: '6px 16px',
            background: 'var(--color-line)',
            borderBottom: '1px solid var(--color-line)',
            color: 'var(--color-ink-3)',
          }}
        >
          Showing placeholder data — backend composer (BE-6, PR #57) is not yet merged.
        </div>
      )}

      <header
        className="flex items-baseline gap-3 flex-wrap"
        style={{
          padding: '20px 24px 16px 24px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <h1
          className="font-serif text-[28px] leading-tight"
          style={{ color: 'var(--color-ink)' }}
        >
          {entity.canonical_name}
        </h1>
        <span
          className="text-[11px] font-medium uppercase tracking-wide"
          style={{
            padding: '2px 8px',
            borderRadius: '4px',
            background: 'var(--color-line)',
            color: 'var(--color-ink-2)',
          }}
        >
          {entity.type}
        </span>
        <span className="text-[12px] ml-auto" style={{ color: 'var(--color-ink-4)' }}>
          Last updated {new Date(entity.updated_at).toLocaleDateString()}
        </span>
      </header>

      <div className="flex-1 grid overflow-hidden" style={{ gridTemplateColumns: '240px 1fr 320px' }}>
        {/* Identity rail */}
        <aside
          className="overflow-y-auto"
          style={{
            padding: '20px',
            borderRight: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
          }}
          aria-label="Identity"
        >
          {entity.aliases.length > 0 && (
            <IdentityBlock title="Aliases">
              <ul className="space-y-1">
                {entity.aliases.map((a) => (
                  <li key={a} className="text-[13px]" style={{ color: 'var(--color-ink-2)' }}>{a}</li>
                ))}
              </ul>
            </IdentityBlock>
          )}
          {Object.keys(entity.external_ids).length > 0 && (
            <IdentityBlock title="External IDs">
              <dl className="space-y-1">
                {Object.entries(entity.external_ids).map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-2">
                    <dt className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--color-ink-4)' }}>{k}</dt>
                    <dd className="text-[12px] font-mono" style={{ color: 'var(--color-ink-2)' }}>{v}</dd>
                  </div>
                ))}
              </dl>
            </IdentityBlock>
          )}
          {Object.keys(entity.primary_attributes).length > 0 && (
            <IdentityBlock title="Attributes">
              <dl className="space-y-1">
                {Object.entries(entity.primary_attributes).map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-2">
                    <dt className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--color-ink-4)' }}>{k.replace(/_/g, ' ')}</dt>
                    <dd className="text-[12px]" style={{ color: 'var(--color-ink-2)' }}>{v ?? '—'}</dd>
                  </div>
                ))}
              </dl>
            </IdentityBlock>
          )}
        </aside>

        {/* Synthesis main */}
        <main
          className="overflow-y-auto"
          style={{ padding: '24px 32px', background: 'var(--color-surface)' }}
          aria-label="Synthesis"
        >
          {synthesis ? (
            <p
              className="font-serif text-[16px] leading-relaxed"
              style={{ color: 'var(--color-ink)' }}
            >
              {synthesis.summary}
            </p>
          ) : (
            <p className="text-[13px] italic" style={{ color: 'var(--color-ink-4)' }}>
              Synthesis pending — the LLM has not yet composed a narrative for this entity.
            </p>
          )}
        </main>

        {/* Evidence pile */}
        <aside
          className="overflow-y-auto"
          style={{
            padding: '20px',
            borderLeft: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
          }}
          aria-label="Evidence"
        >
          <h2 className="text-[11px] uppercase tracking-wide mb-3" style={{ color: 'var(--color-ink-4)' }}>
            Evidence
          </h2>
          {visibleEvidence.length === 0 ? (
            <p className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>No evidence on file yet.</p>
          ) : (
            <ul className="space-y-3">
              {visibleEvidence.map((ev) => (
                <li key={ev.id}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-medium" style={{ color: 'var(--color-ink-2)' }}>
                      {ev.source_name}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-ink-4)' }}>
                      {TIER_LABEL[ev.tier]}
                    </span>
                  </div>
                  <div className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
                    {new Date(ev.published_at).toLocaleDateString()}
                  </div>
                  <p className="text-[12px] mt-1" style={{ color: 'var(--color-ink-3)' }}>{ev.snippet}</p>
                </li>
              ))}
            </ul>
          )}
          {hiddenCount > 0 && (
            <button
              type="button"
              className="text-[12px] mt-3 underline"
              style={{ color: 'var(--color-accent)', cursor: 'pointer' }}
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
  return (
    <div
      className="flex flex-col h-screen"
      style={{ background: 'var(--color-surface)', color: 'var(--color-ink)' }}
    >
      {children}
    </div>
  );
}

function CenteredMessage({ heading, body }: { heading: string; body: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2" style={{ padding: '40px' }}>
      <h2 className="font-serif text-[20px]" style={{ color: 'var(--color-ink)' }}>{heading}</h2>
      <p className="text-[13px] text-center max-w-md" style={{ color: 'var(--color-ink-3)' }}>{body}</p>
    </div>
  );
}

function IdentityBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="text-[11px] uppercase tracking-wide mb-2" style={{ color: 'var(--color-ink-4)' }}>{title}</h3>
      {children}
    </section>
  );
}
