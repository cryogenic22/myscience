import { useState } from 'react';
import { motion } from 'framer-motion';
import { FlaskConical, Shield, Flag, Building2, FileText, ExternalLink, Network } from 'lucide-react';
import type { Message } from '../ChatMessage';
import type { EvidenceItem, GraphNode, GraphEdge } from '../../api';
import { SOURCE_LABELS } from '../../brand';

const PROMPT_ARTIFACT_RE = /\[(metrics|data|evidence|context|sources?|analysis|summary)\]/gi;

function cleanPromptArtifacts(text: string): string {
  return text.replace(PROMPT_ARTIFACT_RE, '').replace(/\s{2,}/g, ' ').trim();
}

interface NarrativeMessageProps {
  message: Message;
  isUser: boolean;
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
  onViewInGraph?: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

export default function NarrativeMessage({
  message,
  isUser,
  onFollowUp,
  onCitationClick,
  onViewInGraph,
}: NarrativeMessageProps) {
  const graphNodes = message.data?.graph_context?.nodes;
  const graphEdges = message.data?.graph_context?.edges;
  const hasGraphContext = Array.isArray(graphNodes) && graphNodes.length > 0;
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
                  entityMentions={
                    (message.data?.entity_focus as Array<Record<string, unknown>> | undefined)
                      ?.map(ef => ({
                        name: String(ef.label || ef.title || ef.generic_name || ef.name || ''),
                        type: String(ef.entity_type || 'drug'),
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

              {/* View in Graph button */}
              {onViewInGraph && hasGraphContext && (
                <button
                  type="button"
                  data-testid="view-in-graph-btn"
                  onClick={() => onViewInGraph(graphNodes!, graphEdges ?? [])}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    marginTop: '12px',
                    padding: '0',
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: 'var(--color-accent)',
                    fontFamily: 'var(--font-body, "DM Sans", sans-serif)',
                    fontWeight: 500,
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.textDecoration = 'underline';
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.textDecoration = 'none';
                  }}
                >
                  <Network size={13} />
                  <span>View in Graph</span>
                  <span style={{ fontSize: '11px' }}>&rarr;</span>
                </button>
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
        result.push({ type: 'entity', text: remaining.slice(idx, idx + entity.name.length), entityType: entity.type });
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
}

function RichText({
  text,
  evidence,
  onCitationClick,
  entityMentions,
}: {
  text: string;
  evidence?: EvidenceItem[];
  onCitationClick?: (index: number) => void;
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
                const color = ENTITY_COLORS[part.entityType || ''] || 'var(--color-accent)';
                return (
                  <span
                    key={i}
                    style={{
                      color,
                      fontWeight: 500,
                      borderBottom: `1.5px solid ${color}40`,
                      cursor: 'default',
                    }}
                    title={`${part.entityType?.replace(/_/g, ' ')} entity`}
                  >
                    {part.text}
                  </span>
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
