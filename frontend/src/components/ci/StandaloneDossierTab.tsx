/**
 * IX-3 — StandaloneDossierTab.
 *
 * The "light path": build an 8-domain, fact-grounded dossier for ANY asset
 * without starting a full engagement. Reuses the engagement dossier engine
 * (via /dossier-preview) and the same EngagementDossierPage + ProvenancePanel
 * surfaces. Promote to a full engagement when the work warrants it.
 */
import { useEffect, useState } from 'react';
import { dossierPreviewApi, type DossierSnapshotDTO } from '../../api';
import {
  EngagementDossierPage,
  type DomainView,
  type DossierDomain,
  type Fact,
} from '../../pages/EngagementDossierPage';
import ProvenancePanel from './ProvenancePanel';

interface Props {
  /** Promote the current asset to a full engagement (e.g. open the create flow). */
  onPromote?: (asset: string) => void;
  /** PB-IX01 — seed the asset (e.g. from a signal promote) and auto-build. */
  initialAsset?: string;
}

function toDomainViews(snapshot: DossierSnapshotDTO): DomainView[] {
  return snapshot.domains.map((d) => ({
    domain: d.domain as DossierDomain,
    priority: d.priority,
    state: d.state,
    readiness: d.readiness,
    facts: d.facts.map((f) => ({
      id: f.id, claim: f.claim, factClass: f.factClass,
      sourceLabel: f.sourceLabel, sourceUrl: f.sourceUrl,
    })),
  }));
}

export default function StandaloneDossierTab({ onPromote, initialAsset }: Props) {
  const [asset, setAsset] = useState(initialAsset || 'semaglutide');
  const [snapshot, setSnapshot] = useState<DossierSnapshotDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openFact, setOpenFact] = useState<Fact | null>(null);

  // PB-IX01 — when seeded from a signal promote, build immediately so the user
  // lands on the dossier, not an empty form.
  useEffect(() => {
    if (initialAsset && initialAsset.trim()) {
      setAsset(initialAsset);
      build(initialAsset);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAsset]);

  const build = async (a: string) => {
    const target = a.trim();
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await dossierPreviewApi.get(target));
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="standalone-dossier">
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: 'var(--color-ink-3)', marginBottom: 8,
        }}>
          Dossier · standalone — build an evidence base on any asset
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            data-testid="dossier-asset-input"
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') build(asset); }}
            placeholder="asset, e.g. semaglutide or drug:semaglutide"
            style={{
              width: 320, padding: '8px 11px', fontSize: 13.5,
              fontFamily: 'var(--font-body)', background: 'var(--color-bg)',
              border: '1px solid var(--color-line)', borderRadius: 8, color: 'var(--color-ink)',
            }}
          />
          <button
            data-testid="dossier-build"
            onClick={() => build(asset)}
            disabled={loading || !asset.trim()}
            style={{
              padding: '9px 16px', fontSize: 13, fontWeight: 500,
              borderRadius: 'var(--radius-pill)', border: 'none',
              cursor: loading ? 'wait' : 'pointer',
              background: 'var(--color-ink)', color: 'var(--color-bg)',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Building…' : 'Build dossier'}
          </button>
          {snapshot && onPromote && (
            <button
              data-testid="dossier-promote"
              onClick={() => onPromote(asset.trim())}
              style={{
                padding: '9px 16px', fontFamily: 'var(--font-mono)', fontSize: 11,
                letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600,
                borderRadius: 'var(--radius-pill)', border: '1px solid var(--color-accent)',
                background: 'var(--color-accent)', color: 'var(--color-surface)', cursor: 'pointer',
              }}
            >
              Promote to full engagement →
            </button>
          )}
        </div>
        <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--color-ink-3)' }}>
          Ephemeral preview — assembled from the facts ledger + knowledge model. Promote to keep it as an engagement.
        </p>
      </div>

      {error && (
        <div data-testid="dossier-preview-error" style={{ color: 'var(--color-red)', fontFamily: 'var(--font-mono)', fontSize: 13, padding: 'var(--space-4)' }}>
          {error}
        </div>
      )}

      {loading && !snapshot && (
        <div data-testid="dossier-preview-loading" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-3)', padding: 'var(--space-5)' }}>
          Assembling dossier for {asset}…
        </div>
      )}

      {snapshot && (
        <div data-testid="dossier-preview-ready">
          <EngagementDossierPage
            scope={{ focalAsset: snapshot.focal_asset, engagementName: 'Standalone dossier' }}
            domains={toDomainViews(snapshot)}
            engagementReadiness={snapshot.readiness}
            onJumpToDomain={(domain) => {
              const el = document.getElementById(`dossier-domain-${domain}`);
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
            onOpenFact={(fact) => setOpenFact(fact)}
          />
          <ProvenancePanel fact={openFact} onClose={() => setOpenFact(null)} />
        </div>
      )}
    </div>
  );
}
