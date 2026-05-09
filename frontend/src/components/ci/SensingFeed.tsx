import React, { useEffect, useState } from 'react';
import { api } from '../../api';
import { HeroCard } from '../primitives/HeroCard';
import { MetricRing } from '../primitives/MetricRing';
import { AgentStatusBar } from '../primitives/AgentStatusBar';

export interface IntelligenceFeedItem {
  event_id: string;
  event_type: string;
  event_date: string;
  description: string;
  source_url: string | null;
  source_tier: string;
  trust_score: number;
  primary_entity_name: string;
  primary_entity_type: string;
  severity: string;
  impact_count: number;
  max_impact_magnitude: number;
  status: string;
  created_at: string;
}

export interface FeedSummary {
  total_unread: number;
  critical_count: number;
  high_count: number;
  since_hours: number;
}

export function SensingFeed() {
  const [items, setItems] = useState<IntelligenceFeedItem[]>([]);
  const [summary, setSummary] = useState<FeedSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [feedData, summaryData] = await Promise.all([
          api.intelligenceFeed({ limit: 10 }),
          api.intelligenceFeedSummary(24)
        ]);
        setItems(feedData.items);
        setSummary(summaryData);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[400px]">
        <AgentStatusBar status="sensing" message="Sensing the market..." agentCount={3} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-medium" style={{ color: 'var(--color-ink)', fontFamily: 'var(--font-display)' }}>Sensing Feed</h2>
          <p className="text-sm" style={{ color: 'var(--color-ink-3)' }}>
            Always-on signal monitoring. {summary?.total_unread || 0} unread signals.
          </p>
        </div>
        <AgentStatusBar status="idle" message="Monitoring" agentCount={3} />
      </div>

      {items.map(item => (
        <HeroCard key={item.event_id} title={`SIGNAL: ${item.primary_entity_name || 'MARKET'}`}>
          <div className="flex gap-6">
            {/* Left col: Score */}
            <div className="flex flex-col items-center justify-center gap-2 w-24">
              <MetricRing value={item.max_impact_magnitude || item.trust_score} size={64} />
              <span className="text-[10px] font-mono tracking-widest uppercase text-center" style={{ color: 'var(--color-ink-3)' }}>Materiality</span>
            </div>
            
            {/* Right col: Details */}
            <div className="flex-1 flex flex-col gap-2">
              <div className="flex justify-between items-start">
                <p className="text-sm font-medium leading-relaxed" style={{ color: 'var(--color-ink)' }}>{item.description}</p>
                <span className="text-xs font-mono px-2 py-1 rounded" style={{ backgroundColor: 'var(--color-surface-3)', color: 'var(--color-ink-2)' }}>
                  {item.source_tier}
                </span>
              </div>
              
              <div className="flex justify-between items-end mt-auto pt-4 border-t" style={{ borderColor: 'var(--color-line-2)' }}>
                <span className="text-xs font-mono" style={{ color: 'var(--color-ink-4)' }}>{item.created_at.split('T')[0]}</span>
                <button 
                  className="text-xs font-semibold uppercase tracking-wider transition-opacity hover:opacity-80 px-4 py-2 rounded"
                  style={{ backgroundColor: 'var(--color-accent)', color: '#fff' }}
                >
                  Frame as Decision
                </button>
              </div>
            </div>
          </div>
        </HeroCard>
      ))}
    </div>
  );
}
