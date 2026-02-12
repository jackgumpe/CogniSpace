import { EventEnvelope } from "../contracts/eventEnvelope";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

type CounterRow = {
  key: string;
  count: number;
};

type SessionHealthRow = {
  session_id: string;
  health_score: number;
};

export type GlobalAnalysisResponse = {
  session_count: number;
  total_events: number;
  mean_health_score: number;
  recurring_event_types: Array<{ key: string; sessions: number }>;
  recurring_motifs_bigram: Array<{ key: string; sessions: number }>;
  outlier_sessions: Array<{ session_id: string; health_score: number; anomaly_count: number }>;
  session_health: SessionHealthRow[];
  selected_session_ids: string[];
  raw: boolean;
};

export type SessionSummaryResponse = {
  session_id: string;
  count: number;
  first_ts: string | null;
  last_ts: string | null;
  actors: string[];
  channels: string[];
  raw: boolean;
};

export type ReplayEvent = EventEnvelope & {
  sequence: number;
};

export type SessionEventsResponse = {
  session_id: string;
  since_event_id: string | null;
  offset: number;
  limit: number;
  next_offset: number | null;
  total_after_since: number;
  events: ReplayEvent[];
  ordered: boolean;
  gap_free: boolean;
  deterministic: boolean;
  raw: boolean;
};

export type SessionAnalysisResponse = {
  session_id: string;
  event_count: number;
  health_score: number;
  window?: {
    first_ts: string;
    last_ts: string;
    duration_seconds: number;
  };
  resource_usage?: {
    token_in_total: number;
    token_out_total: number;
    cost_total_usd: number;
    latency_ms: {
      p50: number;
      p95: number;
      mean: number;
    };
  };
  distribution?: {
    top_event_types: CounterRow[];
    top_actors: CounterRow[];
  };
  pattern_mining?: {
    top_motifs_bigram: CounterRow[];
    top_motifs_trigram: CounterRow[];
    churn_ratio: number;
  };
  interaction_graph?: {
    top_actor_handoffs: CounterRow[];
    transition_pairs: CounterRow[];
  };
  signals?: Record<string, number>;
  burst_windows?: Array<Record<string, unknown>>;
  anomalies: Array<{ code: string; severity: string; value?: number }>;
  recommendations: string[];
  raw: boolean;
};

type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, params?: Record<string, QueryValue>): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      url.searchParams.set(key, String(value));
    });
  }
  return `${url.pathname}${url.search}`;
}

async function fetchJson<T>(path: string, params?: Record<string, QueryValue>): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: { Accept: "application/json" }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body.slice(0, 500)}`);
  }

  return (await response.json()) as T;
}

export async function fetchGlobalAnalysis(params?: {
  raw?: boolean;
  limit_sessions?: number;
  bucket_seconds?: number;
  top_n?: number;
}): Promise<GlobalAnalysisResponse> {
  return fetchJson<GlobalAnalysisResponse>("/logs/analytics/global", params);
}

export async function fetchSessionSummary(
  sessionId: string,
  params?: { raw?: boolean }
): Promise<SessionSummaryResponse> {
  return fetchJson<SessionSummaryResponse>(`/logs/sessions/${sessionId}`, params);
}

export async function fetchSessionEvents(
  sessionId: string,
  params?: { raw?: boolean; since?: string; limit?: number; offset?: number }
): Promise<SessionEventsResponse> {
  return fetchJson<SessionEventsResponse>(`/logs/sessions/${sessionId}/events`, params);
}

export async function fetchSessionAnalysis(
  sessionId: string,
  params?: { raw?: boolean; bucket_seconds?: number; top_n?: number }
): Promise<SessionAnalysisResponse> {
  return fetchJson<SessionAnalysisResponse>(`/logs/sessions/${sessionId}/analysis`, params);
}
