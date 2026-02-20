/**
 * Phase 4.8: Shared types for API meta contracts.
 */

export type MetaTimeContract = {
  data_min_ts?: string | null;
  data_max_ts?: string | null;
  anchor_ts?: string | null;
  effective_window?: { start_ts?: string; end_ts?: string; start?: string; end?: string } | string | null;
  window_source?: string | null;
  timezone?: string | null;
  message?: string | null;
};

export type MetaCache = {
  response_cache?: {
    hit?: boolean;
    key_hash?: string | null;
    ttl_seconds?: number;
  };
  model_cache?: {
    hit?: boolean;
    key_hash?: string | null;
    ttl_seconds?: number;
  };
};

export type MetaEval = {
  metrics?: Record<string, number>;
  test_points?: number;
  train_points?: number;
  horizon?: number;
  granularity?: string;
  points_used?: number;
  window?: number;
  backtest_window?: { start_ts?: string; end_ts?: string };
} | null;

export type MetaExplainFeature = {
  name: string;
  raw_feature: string;
  effect: 'increase' | 'decrease';
  coef: number;
  weight: number;
};

export type MetaExplain = {
  features: MetaExplainFeature[];
  method?: string;
  notes?: string;
} | null;

export type ApiMeta = MetaTimeContract & MetaCache & {
  eval?: MetaEval;
  explain?: MetaExplain;
};
