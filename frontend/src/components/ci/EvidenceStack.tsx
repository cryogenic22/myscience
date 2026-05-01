import type { Signal } from '../../api';

export default function EvidenceStack({ signal }: { signal: Signal }) {
  if (signal.evidence_document_ids.length === 0) {
    return (
      <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
        No evidence documents linked.
      </div>
    );
  }

  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderRadius: '6px',
        overflow: 'hidden',
      }}
    >
      {signal.evidence_document_ids.map((docId, idx) => (
        <div
          key={docId}
          className="flex items-center justify-between text-[12px]"
          style={{
            padding: '10px 14px',
            borderBottom:
              idx < signal.evidence_document_ids.length - 1
                ? '1px solid var(--color-line)'
                : 'none',
          }}
        >
          <div>
            <div
              className="font-mono text-[11px] truncate"
              style={{ color: 'var(--color-ink)', maxWidth: '320px' }}
              title={docId}
            >
              {docId}
            </div>
            <div
              className="text-[10px] mt-0.5 uppercase"
              style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
            >
              source document
            </div>
          </div>
          <span
            className="text-[10px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            #{idx + 1}
          </span>
        </div>
      ))}
    </div>
  );
}
