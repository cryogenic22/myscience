import { useMemo, useRef, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import { Bot, User, ShieldCheck, ShieldAlert, Send } from 'lucide-react';
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
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex gap-2.5 justify-end"
      >
        <div className="max-w-[85%] rounded-xl rounded-tr-sm bg-brand px-4 py-2.5 text-[13px] leading-relaxed text-white">
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-surface-hover">
          <User size={12} className="text-ink-soft" />
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex gap-2.5"
    >
      {/* Bot avatar */}
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-brand/10">
        <Bot size={12} className="text-brand" />
      </div>

      <div className="min-w-0 max-w-[85%]">
        {message.loading ? (
          <div className="rounded-xl rounded-tl-sm bg-surface px-4 py-3">
            <div className="flex gap-1">
              <div className="h-1.5 w-1.5 rounded-full bg-ink-soft/40 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="h-1.5 w-1.5 rounded-full bg-ink-soft/40 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="h-1.5 w-1.5 rounded-full bg-ink-soft/40 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        ) : (
          <>
            {/* Message bubble */}
            <div className="rounded-xl rounded-tl-sm bg-surface px-4 py-2.5 text-[13px] leading-relaxed text-ink">
              <RichText
                text={message.content}
                evidence={message.data?.evidence as EvidenceItem[] | undefined}
                onCitationClick={onCitationClick}
              />

              {/* Guard warning inside bubble */}
              {message.confidenceAssessment && message.confidenceAssessment.overall < 0.5 && (
                <div className="mt-2 flex items-center gap-1.5 border-t border-amber-200/50 pt-2 text-[10px] text-amber-600">
                  <ShieldAlert size={10} />
                  <span>Some details may be approximate. Verify specifics in the data canvas.</span>
                </div>
              )}
            </div>

            {/* Follow-up suggestions — outside bubble */}
            {onFollowUp && message.followupSuggestions && message.followupSuggestions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {message.followupSuggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => onFollowUp(q)}
                    className="rounded-lg bg-surface px-3 py-1.5 text-[11px] text-ink-soft transition-all hover:bg-surface-hover hover:text-ink"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}

/* ── RichText parser ── */

function RichText({
  text,
  evidence,
  onCitationClick,
}: {
  text: string;
  evidence?: EvidenceItem[];
  onCitationClick?: (index: number) => void;
}) {
  const parts = useMemo(() => parseRichText(text), [text]);

  return (
    <>
      {parts.map((part, i) => {
        if (part.type === 'bold') return <strong key={i} className="font-semibold text-ink">{part.text}</strong>;
        if (part.type === 'italic') return <em key={i}>{part.text}</em>;
        if (part.type === 'citation') {
          const idx = parseInt(part.text, 10);
          const ev = evidence?.[idx - 1];
          return (
            <CitationRef
              key={i}
              index={idx}
              evidence={ev}
              onClick={onCitationClick ? () => onCitationClick(idx) : undefined}
            />
          );
        }
        return <span key={i}>{part.text}</span>;
      })}
    </>
  );
}

interface TextPart { type: 'text' | 'bold' | 'italic' | 'citation'; text: string; }

function parseRichText(text: string): TextPart[] {
  const parts: TextPart[] = [];
  const regex = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(\[(\d+)\])/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push({ type: 'text', text: text.slice(lastIndex, match.index) });
    if (match[1]) parts.push({ type: 'bold', text: match[2] });
    else if (match[3]) parts.push({ type: 'italic', text: match[4] });
    else if (match[5]) parts.push({ type: 'citation', text: match[6] });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) parts.push({ type: 'text', text: text.slice(lastIndex) });
  return parts;
}

function CitationRef({ index, evidence, onClick }: { index: number; evidence?: EvidenceItem; onClick?: () => void }) {
  const [showTooltip, setShowTooltip] = useState(false);
  return (
    <span className="relative inline-block">
      <span
        className="cursor-pointer rounded bg-brand/10 px-1 py-0.5 text-[10px] font-semibold text-brand transition-colors hover:bg-brand/20"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onClick={onClick}
        role="button"
        tabIndex={0}
      >
        [{index}]
      </span>
      {showTooltip && evidence && (
        <div className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-xl bg-white p-3 text-[11px] shadow-lg ring-1 ring-black/5">
          <div className="font-medium text-ink line-clamp-2">{evidence.content}</div>
          {evidence.source && <div className="mt-1 text-[10px] text-ink-soft">{evidence.source}</div>}
        </div>
      )}
    </span>
  );
}
