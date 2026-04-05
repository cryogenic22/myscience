import { useState, useRef, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { FlaskConical, Shield, Flag, Building2, FileText, ExternalLink } from 'lucide-react';
import type { Message } from '../ChatMessage';
import type { EvidenceItem, EntitySummary } from '../../api';
import { api } from '../../api';
import { SOURCE_LABELS, ENTITY_TYPE_LABELS, LINK_TYPE_LABELS } from '../../brand';

const PROMPT_ARTIFACT_RE = /\[(metrics|data|evidence|context|sources?|analysis|summary)\]/gi;

function cleanPromptArtifacts(text: string): string {
  return text.replace(PROMPT_ARTIFACT_RE, '').replace(/\s{2,}/g, ' ').trim();
}

interface NarrativeMessageProps {
  message: Message;
  isUser: boolean;
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
  onEntityClick?: (entityId: string, entityType: string) => void;
}

export default function NarrativeMessage({
  message,
  isUser,
  onFollowUp,
  onCitationClick,
  onEntityClick,
}: NarrativeMessageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      {isUser ? (
        /* User message — right-aligned, subtle pill */
        <div className="flex justify-end">
          <div
            className="chat-user-bubble"
            style={{ fontSize: '14px', lineHeight: 1.65 }}
          >
            {message.content}
          </div>
        </div>
      ) : (
        /* Assistant message — left-aligned, plain text, Claude-style */
        <div>
          {message.loading ? (
            <LoadingDots />
          ) : (
            <>
              <div className="chat-assistant-text">
                <RichText
                  text={cleanPromptArtifacts(message.content)}
                  evidence={message.data?.evidence as EvidenceItem[] | undefined}
                  onCitationClick={onCitationClick}
                  onEntityClick={onEntityClick}
                  entityMentions={
                    (message.data?.entity_focus as Array<Record<string, unknown>> | undefined)
                      ?.map(ef => ({
                        name: String(ef.label || ef.title || ef.generic_name || ef.name || ''),
                        type: String(ef.entity_type || 'drug'),
                        entityId: ef.entity_id ? String(ef.entity_id) : undefined,
                      }))
                      .filter(m => m.name.length >= 3)
                  }
                />
              </div>

              {/* Confidence warning */}
              {message.confidenceAssessment && message.confidenceAssessment.overall < 0.45 && (
                <div
                  className="mt-4 flex items-start gap-2 rounded-xl"
                  style={{
                    padding: '12px',
                    background: 'var(--color-amber-soft)',
                    fontSize: '12px',
                    color: 'var(--color-amber)',
                  }}
                >
                  <span>⚠</span>
                  <span>Some details may be approximate — verify specifics in the data canvas.</span>
                </div>
              )}

              {/* Follow-up suggestions */}
              {onFollowUp && message.followupSuggestions && message.followupSuggestions.length > 0 && (
                <div className="mt-5 flex flex-wrap gap-2">
                  {message.followupSuggestions.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => onFollowUp(q)}
                      className="rounded-full text-[12px] transition-all duration-150"
                      style={{
                        padding: '8px 16px',
                        background: 'var(--color-surface-2)',
                        color: 'var(--color-ink-3)',
                        border: '1px solid var(--color-line)',
                      }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-3)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-ink)';
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)';
                        (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-ink-3)';
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </motion.div>
  );
}

function LoadingDots() {
  return (
    <div className="flex items-center gap-1" style={{ padding: '8px 0' }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-2 w-2 rounded-full"
          style={{
            background: 'var(--color-ink-4)',
            animation: 'pulse-dot 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </div>
  );
}

/* ── Rich text ── */

interface TextPart {
  type: 'text' | 'bold' | 'italic' | 'citation' | 'entity';
  text: string;
  entityType?: string;
  entityId?: string;
}

// Entity type → color mapping (consistent with graph node colors)
const ENTITY_COLORS: Record<string, string> = {
  drug: '#3b82f6', company: '#f59e0b', trial: '#14b8a6',
  mechanism: '#a78bfa', therapeutic_area: '#f43f5e', literature: '#22c55e',
};

function highlightEntities(parts: TextPart[], entities: EntityMention[]): TextPart[] {
  if (!entities.length) return parts;
  // Sort by name length DESC (longest match first)
  const sorted = [...entities].sort((a, b) => b.name.length - a.name.length);
  const result: TextPart[] = [];
  for (const part of parts) {
    if (part.type !== 'text') { result.push(part); continue; }
    let remaining = part.text;
    let found = false;
    for (const entity of sorted) {
      if (entity.name.length < 3) continue;
      const idx = remaining.toLowerCase().indexOf(entity.name.toLowerCase());
      if (idx >= 0) {
        if (idx > 0) result.push({ type: 'text', text: remaining.slice(0, idx) });
        result.push({ type: 'entity', text: remaining.slice(idx, idx + entity.name.length), entityType: entity.type, entityId: entity.entityId });
        remaining = remaining.slice(idx + entity.name.length);
        found = true;
        break; // one entity per text part to avoid overlap
      }
    }
    if (!found || remaining.length > 0) {
      result.push({ type: 'text', text: remaining });
    }
  }
  return result;
}

function parseRichText(text: string): TextPart[] {
  const parts: TextPart[] = [];
  const regex = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(\[(\d+)\])/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', text: text.slice(lastIndex, match.index) });
    }
    if (match[1]) parts.push({ type: 'bold', text: match[2] });
    else if (match[3]) parts.push({ type: 'italic', text: match[4] });
    else if (match[5]) parts.push({ type: 'citation', text: match[6] });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) parts.push({ type: 'text', text: text.slice(lastIndex) });
  return parts;
}

interface EntityMention {
  name: string;
  type: string;
  entityId?: string;
}

/* ── Entity popover cache ── */
const entitySummaryCache: Record<string, EntitySummary> = {};

function EntityPopover({
  entityType,
  entityId,
  entityName,
  onEntityClick,
  onMouseEnter,
  onMouseLeave,
}: {
  entityType: string;
  entityId: string;
  entityName: string;
  onEntityClick?: (entityId: string, entityType: string) => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  const [summary, setSummary] = useState<EntitySummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const cacheKey = `${entityType}:${entityId}`;
    if (entitySummaryCache[cacheKey]) {
      setSummary(entitySummaryCache[cacheKey]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    api.entitySummary(entityType, entityId).then((data) => {
      if (!cancelled) {
        entitySummaryCache[cacheKey] = data;
        setSummary(data);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [entityType, entityId]);

  const color = ENTITY_COLORS[entityType] || 'var(--color-accent)';
  const typeLabel = ENTITY_TYPE_LABELS[entityType] || entityType.replace(/_/g, ' ');

  // Top 3 connections by count
  const topConnections = summary
    ? Object.entries(summary.connections_by_type)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 3)
    : [];

  return (
    <div
      data-testid="entity-popover"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        position: 'absolute',
        bottom: 'calc(100% + 8px)',
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: '12px',
        padding: '12px 16px',
        maxWidth: '280px',
        minWidth: '200px',
        boxShadow: '0 4px 16px rgba(0,0,0,0.12), 0 1px 4px rgba(0,0,0,0.06)',
        zIndex: 50,
        opacity: 1,
        transition: 'opacity 150ms ease',
        fontFamily: 'var(--font-body, "DM Sans", sans-serif)',
        fontSize: '12px',
        lineHeight: 1.5,
        color: 'var(--color-ink-2)',
      }}
    >
      {/* Entity type + label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
        <span
          data-testid="entity-popover-dot"
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: color,
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: '10px', color: 'var(--color-ink-4)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
          {typeLabel}
        </span>
      </div>

      {/* Entity name */}
      <div
        data-testid="entity-popover-name"
        style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-ink)', marginBottom: '8px' }}
      >
        {entityName}
      </div>

      {loading ? (
        <div style={{ color: 'var(--color-ink-4)', fontSize: '11px' }}>Loading...</div>
      ) : summary ? (
        <>
          {/* Connections */}
          {topConnections.length > 0 && (
            <div style={{ marginBottom: '8px' }}>
              {topConnections.map(([linkType, count]) => (
                <div
                  key={linkType}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '2px 0',
                    fontSize: '11px',
                  }}
                >
                  <span style={{ color: 'var(--color-ink-3)' }}>
                    {LINK_TYPE_LABELS[linkType] || linkType.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontWeight: 600, color: 'var(--color-ink-2)', marginLeft: '12px' }}>{count}</span>
                </div>
              ))}
            </div>
          )}

          {/* Total connections */}
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginBottom: onEntityClick ? '8px' : 0 }}>
            {summary.total_connections} total connection{summary.total_connections !== 1 ? 's' : ''}
          </div>

          {/* View Profile button */}
          {onEntityClick && (
            <button
              data-testid="entity-popover-view-profile"
              type="button"
              onClick={() => onEntityClick(entityId, entityType)}
              style={{
                display: 'block',
                width: '100%',
                padding: '6px 0',
                background: 'none',
                border: '1px solid var(--color-line)',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--color-accent)',
                textAlign: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none'; }}
            >
              View Profile
            </button>
          )}
        </>
      ) : (
        <div style={{ color: 'var(--color-ink-4)', fontSize: '11px' }}>No summary available</div>
      )}
    </div>
  );
}

function EntityMentionSpan({
  text,
  entityType,
  entityId,
  onEntityClick,
}: {
  text: string;
  entityType: string;
  entityId?: string;
  onEntityClick?: (entityId: string, entityType: string) => void;
}) {
  const color = ENTITY_COLORS[entityType] || 'var(--color-accent)';
  const [showPopover, setShowPopover] = useState(false);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startHover = useCallback(() => {
    if (!entityId) return;
    if (dismissTimerRef.current) { clearTimeout(dismissTimerRef.current); dismissTimerRef.current = null; }
    hoverTimerRef.current = setTimeout(() => {
      setShowPopover(true);
    }, 300);
  }, [entityId]);

  const startDismiss = useCallback(() => {
    if (hoverTimerRef.current) { clearTimeout(hoverTimerRef.current); hoverTimerRef.current = null; }
    dismissTimerRef.current = setTimeout(() => {
      setShowPopover(false);
    }, 200);
  }, []);

  const cancelDismiss = useCallback(() => {
    if (dismissTimerRef.current) { clearTimeout(dismissTimerRef.current); dismissTimerRef.current = null; }
  }, []);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    };
  }, []);

  return (
    <span
      data-testid={entityId ? `entity-mention-${entityId}` : undefined}
      style={{
        position: 'relative',
        display: 'inline',
        color,
        fontWeight: 500,
        borderBottom: `1.5px solid ${color}40`,
        cursor: entityId ? 'pointer' : 'default',
      }}
      title={`${entityType.replace(/_/g, ' ')} entity`}
      onMouseEnter={startHover}
      onMouseLeave={startDismiss}
    >
      {text}
      {showPopover && entityId && (
        <EntityPopover
          entityType={entityType}
          entityId={entityId}
          entityName={text}
          onEntityClick={onEntityClick}
          onMouseEnter={cancelDismiss}
          onMouseLeave={startDismiss}
        />
      )}
    </span>
  );
}

function RichText({
  text,
  evidence,
  onCitationClick,
  onEntityClick,
  entityMentions,
}: {
  text: string;
  evidence?: EvidenceItem[];
  onCitationClick?: (index: number) => void;
  onEntityClick?: (entityId: string, entityType: string) => void;
  entityMentions?: EntityMention[];
}) {
  const paragraphs = text.split(/\n{2,}/);

  return (
    <>
      {paragraphs.map((para, pi) => {
        let parts = parseRichText(para);

        // Highlight entity mentions in text parts
        if (entityMentions?.length) {
          parts = highlightEntities(parts, entityMentions);
        }

        // Check for markdown heading
        const headingMatch = para.match(/^(#{1,3})\s+(.+)/);
        if (headingMatch) {
          const level = headingMatch[1].length;
          const content = headingMatch[2];
          const sizes = { 1: '20px', 2: '17px', 3: '15px' };
          return (
            <p
              key={pi}
              style={{
                fontSize: sizes[level as 1 | 2 | 3] ?? '15px',
                fontWeight: 600,
                color: 'var(--color-ink)',
                marginTop: pi > 0 ? '20px' : 0,
                marginBottom: '8px',
              }}
            >
              {content}
            </p>
          );
        }

        return (
          <p
            key={pi}
            style={{ marginTop: pi > 0 ? '16px' : 0 }}
          >
            {parts.map((part, i) => {
              if (part.type === 'bold') {
                return (
                  <strong
                    key={i}
                    style={{ fontWeight: 600, color: 'var(--color-ink)' }}
                  >
                    {part.text}
                  </strong>
                );
              }
              if (part.type === 'italic') {
                return <em key={i}>{part.text}</em>;
              }
              if (part.type === 'entity') {
                return (
                  <EntityMentionSpan
                    key={i}
                    text={part.text}
                    entityType={part.entityType || 'drug'}
                    entityId={part.entityId}
                    onEntityClick={onEntityClick}
                  />
                );
              }
              if (part.type === 'citation') {
                const idx = parseInt(part.text, 10);
                return (
                  <CitationRef
                    key={i}
                    index={idx}
                    evidence={evidence?.[idx - 1]}
                    onClick={onCitationClick ? () => onCitationClick(idx) : undefined}
                  />
                );
              }
              return (
                <span key={i}>
                  {part.text.split('\n').map((line, li) => (
                    <span key={li}>
                      {li > 0 && <br />}
                      {line}
                    </span>
                  ))}
                </span>
              );
            })}
          </p>
        );
      })}
    </>
  );
}

/* ── Source icon mapping ── */

const SOURCE_ICON_MAP: Record<string, React.ReactNode> = {
  pubmed: <FlaskConical size={10} />,
  pmc: <FlaskConical size={10} />,
  clinical_trials_gov: <Shield size={10} />,
  openfda_faers: <Flag size={10} />,
  openfda_labels: <Flag size={10} />,
  fda_orange_book: <Flag size={10} />,
  fda_shortages: <Flag size={10} />,
  sec_edgar: <Building2 size={10} />,
};

function getSourceIcon(source: string): React.ReactNode {
  const key = source.toLowerCase().replace(/\s+/g, '_');
  return SOURCE_ICON_MAP[key] ?? <FileText size={10} />;
}

function confidenceDotColor(relevance: number): string {
  if (relevance >= 0.8) return '#22c55e'; // green
  if (relevance >= 0.5) return '#f59e0b'; // amber
  return '#ef4444'; // red
}

function CitationRef({
  index,
  evidence,
  onClick,
}: {
  index: number;
  evidence?: EvidenceItem;
  onClick?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const handleClick = () => {
    if (onClick) onClick();
    if (evidence) setExpanded(prev => !prev);
  };

  // Fallback: no evidence data — render plain superscript
  if (!evidence) {
    return (
      <span
        data-testid={`citation-chip-${index}`}
        role="button"
        tabIndex={0}
        className="rounded cursor-default select-none"
        style={{
          padding: '2px 4px',
          fontSize: '10px',
          fontWeight: 600,
          background: 'var(--color-accent-soft)',
          color: 'var(--color-accent)',
          verticalAlign: 'super',
        }}
      >
        [{index}]
      </span>
    );
  }

  const sourceApi = (evidence.provenance?.source_api as string) ?? evidence.source;
  const sourceLabel = SOURCE_LABELS[sourceApi] ?? sourceApi.replace(/_/g, ' ');
  const sourceUrl = evidence.provenance?.source_url as string | undefined;
  const dotColor = confidenceDotColor(evidence.relevance);

  return (
    <span className="inline" data-testid={`citation-chip-${index}`}>
      <span
        role="button"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleClick(); }}
        className="rounded-lg cursor-pointer select-none"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '3px',
          padding: '1px 6px',
          fontSize: '12px',
          fontWeight: 500,
          fontFamily: 'var(--font-body, "DM Sans", sans-serif)',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-line)',
          borderRadius: '10px',
          color: 'var(--color-ink-3)',
          verticalAlign: 'baseline',
          lineHeight: '18px',
          transition: 'background 0.15s, border-color 0.15s',
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLSpanElement).style.background = 'var(--color-surface-3)';
          (e.currentTarget as HTMLSpanElement).style.borderColor = 'var(--color-ink-4)';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLSpanElement).style.background = 'var(--color-surface-2)';
          (e.currentTarget as HTMLSpanElement).style.borderColor = 'var(--color-line)';
        }}
      >
        <span style={{ display: 'inline-flex', opacity: 0.7 }} data-testid={`citation-icon-${index}`}>
          {getSourceIcon(sourceApi)}
        </span>
        <span>{index}</span>
        <span
          data-testid={`citation-dot-${index}`}
          style={{
            display: 'inline-block',
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            background: dotColor,
            flexShrink: 0,
          }}
        />
      </span>

      {/* Expanded evidence card — inline beneath text */}
      {expanded && (
        <span
          data-testid={`citation-evidence-${index}`}
          className="block rounded-xl"
          style={{
            marginTop: '8px',
            marginBottom: '8px',
            padding: '12px 14px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
            boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
            fontSize: '12px',
            lineHeight: 1.6,
            color: 'var(--color-ink-3)',
          }}
        >
          <span className="flex items-center gap-2" style={{ marginBottom: '6px' }}>
            <span style={{ display: 'inline-flex', color: 'var(--color-ink-4)' }}>
              {getSourceIcon(sourceApi)}
            </span>
            <span style={{ fontWeight: 600, color: 'var(--color-ink)', fontSize: '11px' }}>
              {sourceLabel}
            </span>
            <span style={{ color: 'var(--color-ink-4)', fontSize: '10px', textTransform: 'capitalize' }}>
              {evidence.entity_type.replace(/_/g, ' ')}
            </span>
            <span style={{ marginLeft: 'auto', fontSize: '10px', fontWeight: 500, color: 'var(--color-ink-4)' }}>
              {(evidence.relevance * 100).toFixed(0)}% relevant
            </span>
          </span>
          <span className="block" style={{ color: 'var(--color-ink-2)' }}>
            {evidence.content.length > 200 ? evidence.content.slice(0, 198) + '..' : evidence.content}
          </span>
          {sourceUrl && (
            <span className="flex items-center gap-1" style={{ marginTop: '6px', fontSize: '10px', color: 'var(--color-ink-4)' }}>
              <ExternalLink size={10} />
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--color-accent)', textDecoration: 'none' }}
                onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none'; }}
              >
                {sourceUrl.length > 60 ? sourceUrl.slice(0, 58) + '..' : sourceUrl}
              </a>
            </span>
          )}
        </span>
      )}
    </span>
  );
}
