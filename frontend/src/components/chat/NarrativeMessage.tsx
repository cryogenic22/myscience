import { useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { Message } from '../ChatMessage';
import type { EvidenceItem } from '../../api';

interface NarrativeMessageProps {
  message: Message;
  isUser: boolean;
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
}

/**
 * Slimmed-down chat message for the ChatPanel.
 * Renders narrative text only -- no DataTable, no charts, no entity cards.
 */
export default function NarrativeMessage({
  message,
  isUser,
  onFollowUp,
  onCitationClick,
}: NarrativeMessageProps) {
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-md bg-slate-900 px-4 py-3 text-[13px] text-white shadow-sm">
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex justify-start"
    >
      <div className="max-w-[95%] space-y-2">
        {message.loading ? (
          <LoadingDots />
        ) : (
          <>
            {/* Narrative */}
            <div className="px-1 text-[14px] leading-relaxed text-slate-700">
              <RichText
                text={message.content}
                evidence={message.data?.evidence}
                onCitationClick={onCitationClick}
              />
            </div>

            {/* Inline confidence badge */}
            {message.confidenceAssessment && (
              <ConfidenceBadge value={message.confidenceAssessment.overall} />
            )}

            {/* Follow-up chips */}
            {onFollowUp && message.followupSuggestions && message.followupSuggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {message.followupSuggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => onFollowUp(q)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
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

function LoadingDots() {
  return (
    <div className="rounded-md border border-slate-200/70 bg-white/78 px-4 py-4">
      <div className="flex items-center gap-3">
        <div className="flex gap-1">
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="text-xs text-slate-400">Analyzing knowledge graph...</span>
      </div>
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.7
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : value >= 0.4
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-rose-50 text-rose-700 border-rose-200';

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${color}`}>
      Confidence: {pct}%
    </span>
  );
}

/** Citation tooltip showing evidence source on hover. */
function CitationRef({
  index,
  evidence,
  onClick,
}: {
  index: number;
  evidence?: EvidenceItem[];
  onClick?: (index: number) => void;
}) {
  const [show, setShow] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const timeoutRef = useRef<number>(0);

  const item = evidence?.[index - 1]; // citations are 1-based

  const handleEnter = () => {
    clearTimeout(timeoutRef.current);
    setShow(true);
  };
  const handleLeave = () => {
    timeoutRef.current = window.setTimeout(() => setShow(false), 200);
  };

  if (!item) {
    return <sup className="text-[10px] text-slate-400 font-medium">[{index}]</sup>;
  }

  const contentPreview = item.content.length > 120 ? item.content.slice(0, 118) + '..' : item.content;

  return (
    <span className="relative inline-block" ref={ref}>
      <sup
        className="text-[10px] font-semibold text-brand-dark cursor-pointer hover:text-brand transition-colors px-px"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        onClick={() => {
          setShow(!show);
          onClick?.(index);
        }}
      >
        [{index}]
      </sup>
      {show && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-md border border-slate-200 bg-white p-3.5 text-left shadow-lg"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] font-medium text-slate-400 uppercase">{item.source}</span>
            <span className="text-[10px] text-slate-300">|</span>
            <span className="text-[10px] text-slate-400 capitalize">{item.entity_type.replace('_', ' ')}</span>
            <span className="ml-auto text-[10px] font-medium text-slate-400">{(item.relevance * 100).toFixed(0)}%</span>
          </div>
          <p className="text-[11px] text-slate-600 leading-relaxed">{contentPreview}</p>
          <div className="absolute top-full left-1/2 -mt-1 h-2 w-2 -translate-x-1/2 rotate-45 bg-white" />
        </div>
      )}
    </span>
  );
}

/** Render markdown-like text with inline citation support. Reuses the same patterns as ChatMessage.tsx RichText. */
function RichText({
  text,
  evidence,
  onCitationClick,
}: {
  text: string;
  evidence?: EvidenceItem[];
  onCitationClick?: (index: number) => void;
}) {
  const paragraphs = useMemo(() => text.split(/\n{2,}/), [text]);

  return (
    <>
      {paragraphs.map((para, pi) => (
        <p key={pi} className={pi > 0 ? 'mt-2.5' : ''}>
          {para.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[\d+\])/).map((segment, si) => {
            if (segment.startsWith('**') && segment.endsWith('**')) {
              return <strong key={si} className="font-semibold text-slate-800">{segment.slice(2, -2)}</strong>;
            }
            if (segment.startsWith('*') && segment.endsWith('*') && !segment.startsWith('**')) {
              return <em key={si}>{segment.slice(1, -1)}</em>;
            }
            const citationMatch = segment.match(/^\[(\d+)\]$/);
            if (citationMatch) {
              const idx = parseInt(citationMatch[1], 10);
              return <CitationRef key={si} index={idx} evidence={evidence} onClick={onCitationClick} />;
            }
            return segment.split('\n').map((line, li) => (
              <span key={`${si}-${li}`}>
                {li > 0 && <br />}
                {line}
              </span>
            ));
          })}
        </p>
      ))}
    </>
  );
}
