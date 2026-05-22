/**
 * Polish loop — KBQ Dossier page. Route: /ci/dossier/:entityType/:entityId
 * Fetches the per-entity KBQ profile and renders it in the Helix language.
 */
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { kbqApi, type EntityKbqs } from '../api';
import KbqDossier from '../components/ci/KbqDossier';

const H_BG = '#0a0b0e';
const H_INK = '#e8eaed';
const H_DIM = '#8a8f99';

export default function KbqDossierPage() {
  const { entityType = '', entityId = '' } = useParams<{ entityType: string; entityId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<EntityKbqs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    kbqApi.forEntity(entityType, entityId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [entityType, entityId]);

  const shell = (children: React.ReactNode) => (
    <div style={{ background: H_BG, color: H_INK, minHeight: '100vh' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '24px 28px' }}>
        <button
          type="button"
          onClick={() => navigate('/ci')}
          style={{
            background: 'transparent', border: 'none', color: H_DIM, cursor: 'pointer',
            fontSize: 12, fontFamily: "'JetBrains Mono', ui-monospace, monospace",
            letterSpacing: '0.08em', padding: 0, marginBottom: 8,
          }}
        >
          ← BACK TO CI
        </button>
        {children}
      </div>
    </div>
  );

  if (loading) return shell(<p style={{ color: H_DIM }}>Loading dossier…</p>);
  if (error) return shell(<p style={{ color: '#f87171' }}>Could not load dossier: {error}</p>);
  if (!data) return shell(<p style={{ color: H_DIM }}>No dossier data.</p>);

  return (
    <KbqDossier
      data={data}
      entityName={data.entity.name || `${data.entity.type} ${data.entity.id.slice(0, 8)}`}
    />
  );
}
