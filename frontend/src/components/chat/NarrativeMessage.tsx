import { useMemo, useRef, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import { Bot, ShieldCheck, ShieldAlert } from 'lucide-react';
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
        className="flex justify-end"
      >
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-[13.5px] leading-relaxed text-white shadow-sm dark:bg-slate-700">
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex gap-3"
    >
      {/* Avatar */}
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand/15 to-brand/5 ring-1 ring-brand/10">
        <Bot size={14} className="text-brand" />
      </div>

      <div className="min-w-0 flex-1 space-y-2.5">
        {message.loading ? (
          <LoadingPulse />
        ) : (
          <>
            {/* Narrative text */}
            <div className="text-[14px] leading-[1.75] text-slate-700 dark:text-slate-300">
              <RichText
                text={message.content}
                evidence={message.data?.evidence as EvidenceItem[] | undefined}
                onCitationClick={onCitationClick}
              />
            </div>

            {/* Confidence indicator */}
            {message.confidenceAssessment && (
              <ConfidenceIndicator value={message.confidenceAssessment.overall} />
            )}

            {/* Follow-up suggestions */}
            {onFollowUp && message.followupSuggestions && message.followupSuggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2">
                {message.followupSuggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => onFollowUp(q)}
                    className="rounded-full bg-slate-50 px-3.5 py-1.5 text-[11.5px] text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-700 dark:bg-slate-800/50 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
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

/* ── Sub-components ── */

function LoadingPulse() {
  return (
    <div className="flex items-center gap-1.5 py-2">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-2 w-2 rounded-full bg-brand/40 animate-pulse"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

function ConfidenceIndicator({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value > 0.7 ? 'text-emerald-600' : value > 0.4 ? 'text-amber-600' : 'text-red-500';
  const Icon = value > 0.7 ? ShieldCheck : ShieldAlert;

  return (
    <div className={`inline-flex items-center gap-1 text-[10px] font-medium ${color}`}>
      <Icon size={11} />
      <span>{pct}% confidence</span>
    </div>
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
        if (part.type === 'bold') return <strong key={i} className="font-semibold text-slate-900 dark:text-white">{part.text}</strong>;
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

  if (lastIndex < text.length) {
    parts.push({ type: 'text', text: text.slice(lastIndex) });
  }

  return parts;
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
  const [showTooltip, setShowTooltip] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  return (
    <span className="relative inline-block">
      <span
        ref={ref}
        className="cursor-pointer rounded-sm bg-brand/10 px-1 py-0.5 text-[10px] font-semibold text-brand transition-colors hover:bg-brand/20"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onClick={onClick}
        role="button"
        tabIndex={0}
      >
        [{index}]
      </span>
      {showTooltip && evidence && (
        <div className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-3 text-[11px] shadow-lg dark:border-slate-700 dark:bg-slate-800">
          <div className="font-medium text-slate-700 dark:text-slate-200 line-clamp-2">
            {evidence.content}
          </div>
          {evidence.source && (
            <div className="mt-1 text-[10px] text-slate-400">{evidence.source}</div>
          )}
        </div>
      )}
    </span>
  );
}
