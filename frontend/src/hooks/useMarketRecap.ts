/** M4h: Read market recap data from snapshot API. */

import { useState, useEffect, useCallback } from "react";

export interface RecapLeader {
  stock_code: string;
  stock_name: string;
  leader_score: number;
  event_score: number;
  expectation_score: number;
  board_strength_score: number;
  evidence_sources: string[];
  rank_in_theme: number;
}

export interface RecapTheme {
  rank: number;
  theme_name: string;
  strength_score: number;
  stock_count: number;
  leader_count: number;
  avg_leader_score: number;
  resonance_count: number;
  why_strong: string[];
  catalyst: string;
  leaders: RecapLeader[];
  evidence_sources: string[];
}

export interface MarketRecapData {
  version: string;
  trade_date: string;
  top_themes: RecapTheme[];
  market_summary: {
    theme_count: number;
    leader_count: number;
    evidence_source_count: number;
    evidence_sources: string[];
    top_theme: string;
    top_theme_strength: number;
  };
  diagnostics: {
    input_theme_count: number;
    input_leader_count: number;
    input_evidence_count: number;
    degraded: boolean;
    degraded_reasons: string[];
  };
  _meta?: {
    trade_date: string;
    created_at: string;
  };
}

export function useMarketRecap(tradeDate?: string) {
  const [data, setData] = useState<MarketRecapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecap = useCallback(async (date?: string) => {
    setLoading(true);
    setError(null);
    try {
      const path = date
        ? `/api/v2/recap/${date}`
        : "/api/v2/recap/latest";
      const resp = await fetch(path);
      if (!resp.ok) {
        if (resp.status === 404) {
          setData(null);
          setError(`No recap data for ${date || "latest"}`);
          return;
        }
        throw new Error(`recap API ${resp.status}`);
      }
      const json: MarketRecapData = await resp.json();
      setData(json);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "recap load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecap(tradeDate);
  }, [tradeDate, fetchRecap]);

  const refetch = useCallback(
    (date?: string) => fetchRecap(date),
    [fetchRecap],
  );

  return { data, loading, error, refetch };
}
