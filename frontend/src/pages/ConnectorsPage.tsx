import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { connectorsApi, type ConnectorDetail, type ConnectorSummary } from '../api';
import ConnectorList from '../components/connectors/ConnectorList';
import ConnectorDetailView from '../components/connectors/ConnectorDetail';
import { PRODUCT_NAME } from '../brand';

export default function ConnectorsPage() {
  const navigate = useNavigate();
  const [connectors, setConnectors] = useState<ConnectorSummary[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConnectorDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reloadList = useCallback(async () => {
    try {
      const r = await connectorsApi.list();
      setConnectors(r.connectors);
      if (!selectedKey && r.connectors.length > 0) {
        setSelectedKey(r.connectors[0].source_key);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedKey]);

  const reloadDetail = useCallback(async (key: string) => {
    setDetailLoading(true);
    try {
      const d = await connectorsApi.detail(key);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    reloadList();
  }, [reloadList]);

  useEffect(() => {
    if (selectedKey) reloadDetail(selectedKey);
  }, [selectedKey, reloadDetail]);

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--color-surface)' }}>
      {/* Header */}
      <header
        className="shrink-0 flex items-center gap-4"
        style={{
          height: '52px',
          padding: '0 20px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/')}
          className="btn-icon"
          aria-label="Back"
          title="Back"
        >
          <ArrowLeft size={15} />
        </button>
        <span
          className="font-display text-[15px] font-light"
          style={{ color: 'var(--color-ink-3)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>
        <div className="h-4 w-px" style={{ background: 'var(--color-line)' }} />
        <span className="font-display text-[15px]" style={{ color: 'var(--color-ink)' }}>
          Connectors
        </span>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
            Loading connectors…
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-[13px]" style={{ color: '#B91C1C' }}>
            {error}
          </div>
        ) : (
          <>
            <ConnectorList
              connectors={connectors}
              selectedKey={selectedKey}
              onSelect={setSelectedKey}
            />
            {detailLoading || !detail ? (
              <div className="flex-1 flex items-center justify-center text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
                {detailLoading ? 'Loading…' : 'Select a connector'}
              </div>
            ) : (
              <ConnectorDetailView
                detail={detail}
                onChanged={() => {
                  if (selectedKey) reloadDetail(selectedKey);
                  reloadList();
                }}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
