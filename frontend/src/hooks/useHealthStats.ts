import { useEffect, useState } from 'react';
import { api, type CompetitiveSegment, type PortfolioMetric, type SourceCoverageItem } from '../api';

const REFRESH_MS = 30_000;

export interface PlatformStats {
  drugs: number;
  trials: number;
  articles: number;
  companies: number;
  events: number;
  entityLinks: number;
  totalRecords: number;
  connectors: number;
  services: string[];
  sourceCoverage: SourceCoverageItem[];
  competitiveSegments: number;
  topDrug: string;
  topCompany: string;
  loading: boolean;
  error: string | null;
  refreshedAt: string | null;
}

function asCount(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function useHealthStats(): PlatformStats {
  const [stats, setStats] = useState<PlatformStats>({
    drugs: 0,
    trials: 0,
    articles: 0,
    companies: 0,
    events: 0,
    entityLinks: 0,
    totalRecords: 0,
    connectors: 0,
    services: [],
    sourceCoverage: [],
    competitiveSegments: 0,
    topDrug: '',
    topCompany: '',
    loading: true,
    error: null,
    refreshedAt: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [health, competitive, portfolio] = await Promise.all([
          api.health(),
          api.competitive({ limit: 50 }).catch(() => [] as CompetitiveSegment[]),
          api.portfolio({ limit: 5 }).catch(() => [] as PortfolioMetric[]),
        ]);

        if (cancelled) return;

        const tables = health.tables ?? {};
        const sourceCoverage = health.source_coverage ?? [];
        const topPipeline = competitive.length > 0
          ? [...competitive].sort((a, b) => b.total_pipeline_score - a.total_pipeline_score)[0]
          : null;
        const topCo = portfolio.length > 0
          ? [...portfolio].sort((a, b) => b.drug_count - a.drug_count)[0]
          : null;

        const baseCounts = {
          drugs: asCount(tables.drugs),
          trials: asCount(tables.clinical_trials),
          articles: asCount(tables.pubmed_articles),
          companies: asCount(tables.companies),
          events: asCount(tables.market_events),
          entityLinks: asCount(tables.entity_links),
        };
        const totalRecords = asCount(health.total_records) || (
          baseCounts.drugs
          + baseCounts.trials
          + baseCounts.articles
          + baseCounts.companies
          + baseCounts.events
          + baseCounts.entityLinks
        );

        setStats({
          ...baseCounts,
          totalRecords,
          connectors: sourceCoverage.length,
          services: health.services ?? [],
          sourceCoverage,
          competitiveSegments: competitive.length,
          topDrug: topPipeline?.top_drug ?? 'N/A',
          topCompany: topCo?.company_name ?? 'N/A',
          loading: false,
          error: null,
          refreshedAt: health.last_updated ?? new Date().toISOString(),
        });
      } catch (err) {
        if (!cancelled) {
          setStats((prev) => ({
            ...prev,
            loading: false,
            error: String(err),
            refreshedAt: new Date().toISOString(),
          }));
        }
      }
    }

    void load();
    const intervalId = window.setInterval(() => {
      void load();
    }, REFRESH_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  return stats;
}
