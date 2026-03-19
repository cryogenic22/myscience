import { Sparkles } from 'lucide-react';

interface Props {
  onSelect: (query: string) => void;
}

const SUGGESTIONS = [
  'Tell me about semaglutide',
  'Compare semaglutide vs tirzepatide',
  'What is the GLP-1 competitive landscape?',
  'Novo Nordisk company portfolio',
  'Show me the heart failure pipeline',
  'SGLT2 inhibitors in heart failure',
  'Compare empagliflozin vs dapagliflozin',
  'Show me the obesity pipeline',
];

export default function SuggestedQueries({ onSelect }: Props) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-blue-100 bg-white/80">
        <Sparkles size={24} className="text-brand" />
      </div>
      <div className="text-center">
        <h2 className="text-xl font-semibold text-slate-900">
          Ask anything about the pharmaceutical landscape
        </h2>
        <p className="mt-2 text-sm text-slate-500 max-w-md">
          Get evidence-grounded answers powered by {'>'}8,900 knowledge graph connections across drugs, trials, companies, and mechanisms.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2.5 max-w-2xl">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="btn-secondary rounded-lg px-4 py-2 text-sm transition-all"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
