import { IntelligenceFeed } from '../intelligence/IntelligenceFeed';

interface Props {
  onAskInChat?: (question: string) => void;
}

export default function DigestTab({ onAskInChat }: Props) {
  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '20px 24px' }}>
      <div
        className="text-[12px] mb-4"
        style={{
          padding: '10px 14px',
          background: 'var(--color-surface-2)',
          borderRadius: '6px',
          color: 'var(--color-ink-3)',
          border: '1px solid var(--color-line)',
        }}
      >
        <strong>Daily Digest</strong> — assessed events from the intelligence
        pipeline, ordered by trust × recency. The full SPEC-015 signal layer
        (KBQ-tagged, dedup&apos;d, dual-tier-scored) goes live in the{' '}
        <strong>Signals</strong> tab once the clustering service ships.
      </div>
      <IntelligenceFeed onAskInChat={onAskInChat} />
    </div>
  );
}
