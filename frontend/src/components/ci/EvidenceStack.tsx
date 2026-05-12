/**
 * Loop #19 — Evidence Stack.
 *
 * Renders rich cards (source name + tier badge + date + snippet + link)
 * when `documents` metadata is provided. Falls back to unresolved chips
 * when only ids are available so the UI never silently drops evidence.
 */

import type { Signal } from '../../api';
import type { EvidenceDocument, EvidenceTier } from '../../types/evidence';

function tierLabel(tier: EvidenceTier | string | null | undefined): string {
  if (!tier) return 'Unverified';
  const t = String(tier).toLowerCase();
  if (t === 'tier_1' || t === '1') return 'Tier 1';
  if (t === 'tier_2' || t === '2') return 'Tier 2';
  if (t === 'tier_3' || t === '3') return 'Tier 3';
  return 'Unverified';
}

function tierTone(tier: EvidenceTier | string | null | undefined): {
  bg: string;
  fg: string;
  border: string;
} {
  const t = String(tier ?? '').toLowerCase();
  if (t === 'tier_1' || t === '1') {
    return { bg: 'rgba(16, 122, 87, 0.12)', fg: '#0a5a3f', border: 'rgba(16, 122, 87, 0.35)' };
  }
  if (t === 'tier_2' || t === '2') {
    return { bg: 'rgba(31, 96, 161, 0.12)', fg: '#1a4c80', border: 'rgba(31, 96, 161, 0.35)' };
  }
  if (t === 'tier_3' || t === '3') {
    return { bg: 'rgba(167, 117, 18, 0.14)', fg: '#7a5310', border: 'rgba(167, 117, 18, 0.35)' };
  }
  return {
    bg: 'rgba(120, 120, 120, 0.10)',
    fg: 'var(--color-ink-3)',
    border: 'var(--color-line)',
  };
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function sourceDisplayName(source_id: string | undefined | null): string {
  if (!source_id) return 'Source document';
  const map: Record<string, string> = {
    'clinicaltrials.gov': 'ClinicalTrials.gov',
    pubmed: 'PubMed',
    fda_orange_book: 'FDA Orange Book',
    fda_shortages: 'FDA Shortages',
    sec_edgar: 'SEC EDGAR',
    pharma_news: 'Pharma News',
    pubchem: 'PubChem',
    chembl: 'ChEMBL',
  };
  return map[source_id] ?? source_id;
}

function ResolvedCard({ doc, idx, isLast }: { doc: EvidenceDocument; idx: number; isLast: boolean }) {
  const tone = tierTone(doc.source_tier);
  const tierText = tierLabel(doc.source_tier);
  return (
    <div
      data-evidence-card="resolved"
      data-tier={doc.source_tier ?? 'unknown'}
      style={{
        padding: '12px 14px',
        borderBottom: isLast ? 'none' : '1px solid var(--color-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {doc.source_url ? (
            <a
              href={doc.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[13px] font-medium truncate"
              style={{ color: 'var(--color-ink)', textDecoration: 'underline', textUnderlineOffset: 2 }}
            >
              {sourceDisplayName(doc.source_id)}
            </a>
          ) : (
            <span
              className="text-[13px] font-medium truncate"
              style={{ color: 'var(--color-ink)' }}
            >
              {sourceDisplayName(doc.source_id)}
            </span>
          )}
          <span
            data-tier-badge="true"
            className="text-[10px] uppercase tracking-wide"
            style={{
              padding: '2px 6px',
              borderRadius: '999px',
              border: `1px solid ${tone.border}`,
              background: tone.bg,
              color: tone.fg,
              letterSpacing: '0.05em',
              whiteSpace: 'nowrap',
            }}
          >
            {tierText}
          </span>
        </div>
        <span className="text-[11px]" style={{ color: 'var(--color-ink-4)', whiteSpace: 'nowrap' }}>
          {formatDate(doc.retrieved_at)}
        </span>
      </div>
      {doc.snippet ? (
        <p
          className="text-[12px]"
          style={{
            color: 'var(--color-ink-3)',
            lineHeight: 1.5,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            margin: 0,
          }}
        >
          {doc.snippet}
        </p>
      ) : null}
      <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
        <span style={{ letterSpacing: '0.04em' }}>#{idx + 1}</span>
        {typeof doc.confidence === 'number' ? (
          <span>· confidence {(doc.confidence * 100).toFixed(0)}%</span>
        ) : null}
      </div>
    </div>
  );
}

function UnresolvedCard({ docId, idx, isLast }: { docId: string; idx: number; isLast: boolean }) {
  return (
    <div
      data-evidence-card="unresolved"
      className="flex items-center justify-between"
      style={{
        padding: '10px 14px',
        borderBottom: isLast ? 'none' : '1px solid var(--color-line)',
      }}
    >
      <div className="min-w-0">
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
          source document · metadata pending
        </div>
      </div>
      <span className="text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
        #{idx + 1}
      </span>
    </div>
  );
}

interface Props {
  signal: Signal;
  documents?: EvidenceDocument[];
}

export default function EvidenceStack({ signal, documents }: Props) {
  if (signal.evidence_document_ids.length === 0) {
    return (
      <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
        No evidence documents linked.
      </div>
    );
  }

  const byId = new Map<string, EvidenceDocument>();
  for (const d of documents ?? []) {
    byId.set(d.evidence_id, d);
  }

  const rendered = signal.evidence_document_ids.map((docId, idx) => {
    const isLast = idx === signal.evidence_document_ids.length - 1;
    const doc = byId.get(docId);
    if (doc) {
      return <ResolvedCard key={docId} doc={doc} idx={idx} isLast={isLast} />;
    }
    return <UnresolvedCard key={docId} docId={docId} idx={idx} isLast={isLast} />;
  });

  return (
    <div
      style={{
        border: '1px solid var(--color-line)',
        borderRadius: '6px',
        overflow: 'hidden',
      }}
    >
      {rendered}
    </div>
  );
}
