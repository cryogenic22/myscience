import { useState, useEffect, useRef, useCallback } from 'react';
import {
  X, ChevronDown, ChevronRight, BookOpen, ExternalLink,
  FileText, FlaskConical, Users, Tag, Sparkles, Loader,
} from 'lucide-react';
import { api, type LiteratureDocument, type LiteratureSection, type SimilarArticle } from '../api';

/* ── Props ── */

interface LiteratureExplorerProps {
  articleId: string;
  onClose: () => void;
  onNavigate?: (articleId: string) => void;
}

/* ── Main Component ── */

export function LiteratureExplorer({ articleId, onClose, onNavigate }: LiteratureExplorerProps) {
  const [doc, setDoc] = useState<LiteratureDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string>('');
  const [similarArticles, setSimilarArticles] = useState<SimilarArticle[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSimilarArticles([]);
    setSummary(null);
    api.literatureDocument(articleId)
      .then((d) => { if (!cancelled) { setDoc(d); setActiveSection(d.sections[0]?.id ?? ''); } })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    // Fetch similar articles in parallel
    api.literatureSimilar(articleId, 5)
      .then((r) => { if (!cancelled) setSimilarArticles(r.similar); })
      .catch(() => { /* ignore — similar articles are optional */ });
    return () => { cancelled = true; };
  }, [articleId]);

  const handleNavigate = useCallback((targetId: string) => {
    if (onNavigate) {
      onNavigate(targetId);
    }
  }, [onNavigate]);

  const generateSummary = useCallback(() => {
    setSummaryLoading(true);
    api.literatureSummary(articleId)
      .then((r) => { setSummary(r.summary); })
      .catch(() => { setSummary(null); })
      .finally(() => { setSummaryLoading(false); });
  }, [articleId]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        style={{ background: 'rgba(10,10,11,0.18)', backdropFilter: 'blur(3px)' }}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed inset-y-0 right-0 z-50 flex flex-col animate-slide-in"
        style={{
          width: 'clamp(860px, 80vw, 1200px)',
          maxWidth: '96vw',
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-line)',
          boxShadow: 'var(--shadow-xl)',
        }}
      >
        {/* Header */}
        <div
          className="shrink-0 flex items-start justify-between gap-4"
          style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="flex items-center gap-2" style={{ marginBottom: '4px' }}>
              <BookOpen size={14} style={{ color: 'var(--color-literature)', flexShrink: 0 }} />
              <span style={{ fontSize: '11px', color: 'var(--color-ink-4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {doc?.article_type?.replace(/-/g, ' ') ?? 'Publication'}
              </span>
              {doc?.is_protocol && <Badge label="Protocol" />}
              {doc?.is_systematic_review && <Badge label="Systematic Review" />}
            </div>
            <h2 style={{
              fontSize: '16px', fontWeight: 600, color: 'var(--color-ink)',
              letterSpacing: '-0.02em', lineHeight: 1.35,
              overflow: 'hidden', textOverflow: 'ellipsis',
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
            }}>
              {doc?.title ?? (loading ? 'Loading…' : 'Article')}
            </h2>
            {doc?.journal && (
              <p style={{ fontSize: '12px', color: 'var(--color-ink-3)', marginTop: '2px' }}>
                {doc.journal}{doc.publication_date ? ` · ${doc.publication_date}` : ''}
                {doc.pmid ? ` · PMID ${doc.pmid}` : ''}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="btn-icon shrink-0" aria-label="Close">
            <X size={15} />
          </button>
        </div>

        {/* Body: 3 panels */}
        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-ink-4)' }}>
            <div className="animate-spin" style={{ width: 20, height: 20, border: '2px solid var(--color-line)', borderTopColor: 'var(--color-accent)', borderRadius: '50%' }} />
            <span style={{ marginLeft: 8, fontSize: '13px' }}>Loading article…</span>
          </div>
        ) : error ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-red)', fontSize: '13px', padding: '24px' }}>
            {error}
          </div>
        ) : doc ? (
          <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
            {/* Left: Section Tree */}
            <SectionTree
              sections={doc.sections}
              activeSection={activeSection}
              onSelect={setActiveSection}
            />

            {/* Center: Content */}
            <ContentArea
              sections={doc.sections}
              hasFullText={doc.has_full_text}
              onActiveSectionChange={setActiveSection}
              summary={summary}
              summaryLoading={summaryLoading}
              onGenerateSummary={generateSummary}
            />

            {/* Right: Context */}
            <ContextSidebar
              doc={doc}
              similarArticles={similarArticles}
              onNavigate={handleNavigate}
            />
          </div>
        ) : null}
      </div>
    </>
  );
}

/* ── Section Tree (Left Panel) ── */

function SectionTree({
  sections,
  activeSection,
  onSelect,
}: {
  sections: LiteratureSection[];
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav
      style={{
        width: '220px', flexShrink: 0, overflowY: 'auto',
        background: 'var(--color-surface-2)',
        borderRight: '1px solid var(--color-line)',
        padding: '16px 0',
      }}
    >
      <div style={{ padding: '0 12px 8px', fontSize: '10px', fontWeight: 600, color: 'var(--color-ink-4)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Sections
      </div>
      {sections.map((s) => (
        <SectionTreeItem key={s.id} section={s} activeSection={activeSection} onSelect={onSelect} depth={0} />
      ))}
    </nav>
  );
}

function SectionTreeItem({
  section,
  activeSection,
  onSelect,
  depth,
}: {
  section: LiteratureSection;
  activeSection: string;
  onSelect: (id: string) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = section.children.length > 0;
  const isActive = activeSection === section.id;

  const handleClick = () => {
    onSelect(section.id);
    const el = document.getElementById(section.id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        style={{
          display: 'flex', alignItems: 'center', gap: '4px', width: '100%',
          padding: `4px 12px 4px ${12 + depth * 16}px`,
          background: isActive ? 'var(--color-accent-soft, rgba(28,110,247,0.08))' : 'transparent',
          border: 'none', cursor: 'pointer', textAlign: 'left',
          fontSize: '12px', lineHeight: 1.4,
          color: isActive ? 'var(--color-accent)' : 'var(--color-ink-2)',
          fontWeight: isActive ? 600 : 400,
          borderLeft: isActive ? '2px solid var(--color-accent)' : '2px solid transparent',
        }}
      >
        {hasChildren && (
          <span
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            style={{ flexShrink: 0, display: 'flex', cursor: 'pointer' }}
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        )}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {section.title}
        </span>
      </button>
      {hasChildren && expanded && section.children.map((child) => (
        <SectionTreeItem key={child.id} section={child} activeSection={activeSection} onSelect={onSelect} depth={depth + 1} />
      ))}
    </div>
  );
}

/* ── Content Area (Center Panel) ── */

function ContentArea({
  sections,
  hasFullText,
  onActiveSectionChange,
  summary,
  summaryLoading,
  onGenerateSummary,
}: {
  sections: LiteratureSection[];
  hasFullText: boolean;
  onActiveSectionChange: (id: string) => void;
  summary: string | null;
  summaryLoading: boolean;
  onGenerateSummary: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  // IntersectionObserver for scroll-spy
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            onActiveSectionChange(entry.target.id);
            break;
          }
        }
      },
      { root: container, rootMargin: '-20% 0px -60% 0px', threshold: 0 }
    );

    const headings = container.querySelectorAll('[data-section-heading]');
    headings.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [sections, onActiveSectionChange]);

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1, overflowY: 'auto', padding: '24px 32px',
        fontFamily: 'var(--font-body)', fontSize: '14px', lineHeight: 1.7,
        color: 'var(--color-ink)',
      }}
    >
      {/* AI Summary */}
      <div style={{ marginBottom: '20px' }}>
        {!summary && !summaryLoading && (
          <button
            type="button"
            onClick={onGenerateSummary}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '6px 14px', borderRadius: '8px',
              background: 'var(--color-accent-soft, rgba(28,110,247,0.08))',
              color: 'var(--color-accent)', border: 'none',
              fontSize: '12px', fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Sparkles size={13} />
            Generate Key Findings
          </button>
        )}
        {summaryLoading && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '6px 14px', fontSize: '12px', color: 'var(--color-ink-3)',
          }}>
            <Loader size={13} className="animate-spin" />
            Generating summary...
          </div>
        )}
        {summary && (
          <div style={{
            padding: '12px 16px', borderRadius: '10px',
            background: 'var(--color-accent-soft, rgba(28,110,247,0.06))',
            borderLeft: '3px solid var(--color-accent)',
            fontSize: '13px', lineHeight: 1.6, color: 'var(--color-ink-2)',
            whiteSpace: 'pre-wrap',
          }}>
            <div style={{
              fontSize: '10px', fontWeight: 600, color: 'var(--color-accent)',
              textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px',
            }}>
              Key Findings
            </div>
            {summary}
          </div>
        )}
      </div>

      {!hasFullText && sections.length <= 1 && (
        <div style={{
          padding: '12px 16px', marginBottom: '20px', borderRadius: '8px',
          background: 'var(--color-surface-2)', fontSize: '12px', color: 'var(--color-ink-3)',
        }}>
          Full text not available for this article. Showing abstract only.
        </div>
      )}
      {sections.map((s) => (
        <SectionContent key={s.id} section={s} />
      ))}
    </div>
  );
}

function SectionContent({ section }: { section: LiteratureSection }) {
  return (
    <div style={{ marginBottom: '28px' }}>
      <div id={section.id} data-section-heading style={{ scrollMarginTop: '16px' }}>
        <h3 style={{
          fontSize: section.level === 1 ? '17px' : '14px',
          fontWeight: 600, color: 'var(--color-ink)',
          marginBottom: '10px', letterSpacing: '-0.01em',
          borderBottom: section.level === 1 ? '1px solid var(--color-line)' : 'none',
          paddingBottom: section.level === 1 ? '6px' : '0',
        }}>
          {section.title}
        </h3>
      </div>
      {section.content && (
        <div style={{ whiteSpace: 'pre-wrap', color: 'var(--color-ink-2)' }}>
          {renderParagraphs(section.content)}
        </div>
      )}
      {section.children.map((child) => (
        <div key={child.id} style={{ marginLeft: '16px', marginTop: '20px' }}>
          <SectionContent section={child} />
        </div>
      ))}
    </div>
  );
}

function renderParagraphs(text: string) {
  return text.split(/\n{2,}/).map((para, i) => (
    <p key={i} style={{ marginBottom: '12px' }}>
      {renderInline(para.trim())}
    </p>
  ));
}

function renderInline(text: string) {
  // Bold: **text**
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ fontWeight: 600, color: 'var(--color-ink)' }}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

/* ── Context Sidebar (Right Panel) ── */

function ContextSidebar({
  doc,
  similarArticles,
  onNavigate,
}: {
  doc: LiteratureDocument;
  similarArticles: SimilarArticle[];
  onNavigate: (articleId: string) => void;
}) {
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const visibleAuthors = showAllAuthors ? doc.authors : doc.authors.slice(0, 5);
  const hasMore = doc.authors.length > 5;

  return (
    <aside
      style={{
        width: '280px', flexShrink: 0, overflowY: 'auto',
        borderLeft: '1px solid var(--color-line)',
        padding: '20px 16px', fontSize: '12px',
      }}
    >
      {/* External links — prominent buttons */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '20px' }}>
        {doc.external_urls.pubmed && (
          <a
            href={doc.external_urls.pubmed}
            target="_blank" rel="noopener noreferrer"
            style={{
              fontSize: '11px', padding: '4px 10px', borderRadius: '6px',
              background: 'var(--color-surface-2)', color: 'var(--color-accent)',
              textDecoration: 'none', fontWeight: 500,
            }}
          >
            PubMed &#x2197;
          </a>
        )}
        {doc.external_urls.pmc && (
          <a
            href={doc.external_urls.pmc}
            target="_blank" rel="noopener noreferrer"
            style={{
              fontSize: '11px', padding: '4px 10px', borderRadius: '6px',
              background: 'var(--color-surface-2)', color: 'var(--color-accent)',
              textDecoration: 'none', fontWeight: 500,
            }}
          >
            PMC &#x2197;
          </a>
        )}
        {doc.external_urls.pdf && (
          <a
            href={doc.external_urls.pdf}
            target="_blank" rel="noopener noreferrer"
            style={{
              fontSize: '11px', padding: '4px 10px', borderRadius: '6px',
              background: 'var(--color-green-soft, rgba(5,150,105,0.08))',
              color: 'var(--color-green)',
              textDecoration: 'none', fontWeight: 500,
            }}
          >
            PDF &#x2197;
          </a>
        )}
      </div>

      {/* Journal + Date */}
      {doc.journal && (
        <MetaBlock label="Journal">
          <span style={{ color: 'var(--color-ink)', fontWeight: 500 }}>{doc.journal}</span>
          {doc.publication_date && (
            <span style={{ color: 'var(--color-ink-3)', marginLeft: '6px' }}>{doc.publication_date}</span>
          )}
        </MetaBlock>
      )}

      {/* Identifiers */}
      <MetaBlock label="Identifiers">
        {doc.pmid && <div>PMID: <span style={{ fontWeight: 500 }}>{doc.pmid}</span></div>}
        {doc.pmc_id && <div>PMC: <span style={{ fontWeight: 500 }}>{doc.pmc_id}</span></div>}
      </MetaBlock>

      {/* Authors */}
      {doc.authors.length > 0 && (
        <MetaBlock label="Authors" icon={<Users size={12} />}>
          {visibleAuthors.map((a, i) => (
            <div key={i} style={{ color: 'var(--color-ink-2)', lineHeight: 1.6 }}>{a}</div>
          ))}
          {hasMore && (
            <button
              type="button"
              onClick={() => setShowAllAuthors(!showAllAuthors)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--color-accent)', fontSize: '11px', padding: '2px 0',
              }}
            >
              {showAllAuthors ? 'Show fewer' : `+${doc.authors.length - 5} more`}
            </button>
          )}
        </MetaBlock>
      )}

      {/* MeSH Terms */}
      {doc.mesh_terms.length > 0 && (
        <MetaBlock label="MeSH Terms" icon={<Tag size={12} />}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {doc.mesh_terms.map((term, i) => (
              <span
                key={i}
                style={{
                  display: 'inline-block', padding: '2px 8px', borderRadius: '980px',
                  background: 'var(--color-surface-2)', color: 'var(--color-ink-3)',
                  fontSize: '11px', lineHeight: 1.5,
                }}
              >
                {term}
              </span>
            ))}
          </div>
        </MetaBlock>
      )}

      {/* Linked Drugs */}
      {doc.cross_links.drugs.length > 0 && (
        <MetaBlock label="Linked Drugs" icon={<FlaskConical size={12} />}>
          {doc.cross_links.drugs.map((d) => (
            <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', lineHeight: 1.8, color: 'var(--color-ink-2)' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-drug)', flexShrink: 0 }} />
              {d.name}
            </div>
          ))}
        </MetaBlock>
      )}

      {/* Linked Trials */}
      {doc.cross_links.trials.length > 0 && (
        <MetaBlock label="Linked Trials" icon={<FileText size={12} />}>
          {doc.cross_links.trials.map((t) => (
            <div key={t.id} style={{
              lineHeight: 1.5, color: 'var(--color-ink-2)', marginBottom: '4px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-trial)', display: 'inline-block', marginRight: '6px', flexShrink: 0 }} />
              {t.title}
            </div>
          ))}
        </MetaBlock>
      )}

      {/* Similar Articles */}
      {similarArticles.length > 0 && (
        <MetaBlock label="Similar Articles" icon={<BookOpen size={12} />}>
          {similarArticles.map((a) => (
            <div
              key={a.article_id}
              style={{
                fontSize: '12px', padding: '6px 0',
                borderBottom: '1px solid var(--color-line)',
                cursor: 'pointer',
              }}
              onClick={() => onNavigate(a.article_id)}
            >
              <div style={{
                color: 'var(--color-ink)', fontWeight: 500, lineHeight: 1.4,
                overflow: 'hidden', textOverflow: 'ellipsis',
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              }}>
                {a.title}
              </div>
              <div style={{ color: 'var(--color-ink-4)', fontSize: '11px', marginTop: '2px' }}>
                {a.journal ? `${a.journal}` : ''}
                {a.publication_date ? ` · ${a.publication_date}` : ''}
                {typeof a.similarity === 'number' ? ` · ${Math.round(a.similarity * 100)}% match` : ''}
              </div>
            </div>
          ))}
        </MetaBlock>
      )}
    </aside>
  );
}

/* ── Shared sub-components ── */

function MetaBlock({ label, icon, children }: { label: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '20px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '6px',
        fontSize: '10px', fontWeight: 600, color: 'var(--color-ink-4)',
        textTransform: 'uppercase', letterSpacing: '0.06em',
      }}>
        {icon}
        {label}
      </div>
      {children}
    </div>
  );
}

function Badge({ label }: { label: string }) {
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: '980px',
      background: 'rgba(5, 150, 105, 0.1)', color: 'var(--color-literature)',
      fontSize: '10px', fontWeight: 600, letterSpacing: '0.02em',
    }}>
      {label}
    </span>
  );
}
