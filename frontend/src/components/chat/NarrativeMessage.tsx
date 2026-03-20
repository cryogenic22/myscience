import { useState } from 'react';
import { motion } from 'framer-motion';
import type { Message } from '../ChatMessage';
import type { EvidenceItem } from '../../api';

interface NarrativeMessageProps {
  message: Message;
  isUser: boolean;
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
}

export default function NarrativeMessage({
  message,
  isUser,
  onFollowUp,
  onCitationClick,
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
                  text={message.content}
                  evidence={message.data?.evidence as EvidenceItem[] | undefined}
                  onCitationClick={onCitationClick}
                />
              </div>

              {/* Confidence warning */}
              {message.confidenceAssessment && message.confidenceAssessment.overall < 0.45 && (
                <div
                  className="mt-4 flex items-start gap-2 rounded-xl p-3"
                  style={{
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
                      className="rounded-full px-4 py-2 text-[12px] transition-all duration-150"
                      style={{
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
    <div className="flex items-center gap-1 py-2">
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
  type: 'text' | 'bold' | 'italic' | 'citation';
  text: string;
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

function RichText({
  text,
  evidence,
  onCitationClick,
}: {
  text: string;
  evidence?: EvidenceItem[];
  onCitationClick?: (index: number) => void;
}) {
  const paragraphs = text.split(/\n{2,}/);

  return (
    <>
      {paragraphs.map((para, pi) => {
        const parts = parseRichText(para);

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

function CitationRef({
  index,
  evidence,
  onClick,
}: {
  index: number;
  evidence?: EvidenceItem;
  onClick?: () => void;
}) {
  const [show, setShow] = useState(false);

  return (
    <span className="relative inline-block">
      <span
        role="button"
        tabIndex={0}
        className="rounded px-1 py-0.5 cursor-pointer select-none"
        style={{
          fontSize: '10px',
          fontWeight: 600,
          background: 'var(--color-accent-soft)',
          color: 'var(--color-accent)',
          verticalAlign: 'super',
        }}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={onClick}
      >
        [{index}]
      </span>

      {show && evidence && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-2 rounded-xl p-3 text-left"
          style={{
            width: '260px',
            transform: 'translateX(-50%)',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
            boxShadow: 'var(--shadow-lg)',
            fontSize: '11px',
            lineHeight: 1.5,
            color: 'var(--color-ink-3)',
          }}
        >
          <div
            className="font-medium mb-1 line-clamp-3"
            style={{ color: 'var(--color-ink)' }}
          >
            {evidence.content}
          </div>
          <div style={{ color: 'var(--color-ink-4)' }}>{evidence.source}</div>
        </div>
      )}
    </span>
  );
}
