import { useCallback, useEffect, useMemo, useState } from "react";

import {
  GlobalAnalysisResponse,
  SessionAnalysisResponse,
  SessionEventsResponse,
  SessionSummaryResponse,
  fetchGlobalAnalysis,
  fetchSessionAnalysis,
  fetchSessionEvents,
  fetchSessionSummary
} from "./api/logs";
import { useSessionStore } from "./store/sessionStore";

const PAGE_SIZE = 50;

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) {
    return "-";
  }
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) {
    return ts;
  }
  return parsed.toLocaleString();
}

function formatPayload(payload: unknown): string {
  try {
    const text = JSON.stringify(payload, null, 2);
    if (text.length <= 600) {
      return text;
    }
    return `${text.slice(0, 600)}...`;
  } catch {
    return String(payload);
  }
}

function healthTone(score: number): string {
  if (score >= 85) {
    return "text-success-emphasis bg-success-subtle";
  }
  if (score >= 70) {
    return "text-warning-emphasis bg-warning-subtle";
  }
  return "text-danger-emphasis bg-danger-subtle";
}

export default function App() {
  const { sessionId, setSessionId } = useSessionStore();
  const [rawMode, setRawMode] = useState(false);
  const [globalLoading, setGlobalLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [globalAnalysis, setGlobalAnalysis] = useState<GlobalAnalysisResponse | null>(null);
  const [summary, setSummary] = useState<SessionSummaryResponse | null>(null);
  const [analysis, setAnalysis] = useState<SessionAnalysisResponse | null>(null);
  const [eventsPage, setEventsPage] = useState<SessionEventsResponse | null>(null);

  const sessionHealthMap = useMemo(() => {
    const map = new Map<string, number>();
    globalAnalysis?.session_health.forEach((item) => map.set(item.session_id, item.health_score));
    return map;
  }, [globalAnalysis]);

  const sessionIds = useMemo(
    () => [...(globalAnalysis?.selected_session_ids ?? [])].reverse(),
    [globalAnalysis]
  );

  const loadGlobal = useCallback(async () => {
    setGlobalLoading(true);
    try {
      const data = await fetchGlobalAnalysis({ raw: rawMode, limit_sessions: 150, top_n: 10 });
      setGlobalAnalysis(data);
      setError(null);
      if (!sessionId && data.selected_session_ids.length > 0) {
        setSessionId(data.selected_session_ids[data.selected_session_ids.length - 1]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load global analytics.");
    } finally {
      setGlobalLoading(false);
    }
  }, [rawMode, sessionId, setSessionId]);

  const loadSession = useCallback(async () => {
    if (!sessionId) {
      setSummary(null);
      setAnalysis(null);
      setEventsPage(null);
      return;
    }
    setSessionLoading(true);
    try {
      const [summaryData, analysisData, eventData] = await Promise.all([
        fetchSessionSummary(sessionId, { raw: rawMode }),
        fetchSessionAnalysis(sessionId, { raw: rawMode, top_n: 10 }),
        fetchSessionEvents(sessionId, { raw: rawMode, limit: PAGE_SIZE, offset })
      ]);
      setSummary(summaryData);
      setAnalysis(analysisData);
      setEventsPage(eventData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session details.");
    } finally {
      setSessionLoading(false);
    }
  }, [offset, rawMode, sessionId]);

  useEffect(() => {
    void loadGlobal();
  }, [loadGlobal]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const onSelectSession = (id: string) => {
    setSessionId(id);
    setOffset(0);
  };

  const canPrev = offset > 0;
  const canNext = eventsPage?.next_offset !== null && eventsPage?.next_offset !== undefined;
  const currentHealth = sessionId ? sessionHealthMap.get(sessionId) ?? analysis?.health_score ?? 0 : 0;

  return (
    <div className="app-shell min-vh-100">
      <div className="container-fluid py-3">
        <div className="surface-card p-3 mb-3">
          <div className="d-flex flex-wrap gap-3 align-items-center justify-content-between">
            <div>
              <h1 className="h4 mb-1">CogniSpace History Console</h1>
              <p className="mb-0 text-muted">
                Placeholder utility UI for replaying session history and analytics.
              </p>
            </div>
            <div className="d-flex gap-2 align-items-center">
              <button
                type="button"
                className="btn btn-soft"
                onClick={() => {
                  void loadGlobal();
                  void loadSession();
                }}
                disabled={globalLoading || sessionLoading}
              >
                Refresh
              </button>
              <div className="form-check form-switch mb-0">
                <input
                  className="form-check-input"
                  type="checkbox"
                  role="switch"
                  id="rawMode"
                  checked={rawMode}
                  onChange={(e) => {
                    setRawMode(e.target.checked);
                    setOffset(0);
                  }}
                />
                <label className="form-check-label small" htmlFor="rawMode">
                  Raw payloads
                </label>
              </div>
            </div>
          </div>
          <ul className="nav nav-pills mt-3 tab-row">
            <li className="nav-item">
              <button type="button" className="nav-link active">
                History
              </button>
            </li>
            <li className="nav-item">
              <button type="button" className="nav-link disabled">
                Current
              </button>
            </li>
            <li className="nav-item">
              <button type="button" className="nav-link disabled">
                Live Feed
              </button>
            </li>
          </ul>
        </div>

        {error ? (
          <div className="alert alert-danger py-2" role="alert">
            {error}
          </div>
        ) : null}

        <div className="row g-3">
          <div className="col-12 col-lg-3">
            <div className="surface-card surface-inset p-3 h-100">
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h2 className="h6 mb-0">Sessions</h2>
                <span className="badge bg-primary-subtle text-primary-emphasis">
                  {globalAnalysis?.session_count ?? 0}
                </span>
              </div>
              <p className="small text-muted mb-3">History-first list. Most recent sessions appear first.</p>
              <div className="session-list">
                {sessionIds.length === 0 ? (
                  <p className="small text-muted mb-0">No sessions found yet.</p>
                ) : (
                  sessionIds.map((id) => {
                    const active = id === sessionId;
                    const score = sessionHealthMap.get(id) ?? 0;
                    return (
                      <button
                        key={id}
                        type="button"
                        className={`session-item w-100 text-start ${active ? "active" : ""}`}
                        onClick={() => onSelectSession(id)}
                      >
                        <div className="d-flex justify-content-between align-items-center">
                          <span className="session-id">{id}</span>
                          <span className={`badge ${healthTone(score)}`}>{score.toFixed(1)}</span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div className="col-12 col-lg-6">
            <div className="surface-card p-3 h-100">
              <div className="d-flex justify-content-between align-items-center mb-2">
                <h2 className="h6 mb-0">Session Events</h2>
                <div className="d-flex align-items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary"
                    disabled={!canPrev}
                    onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary"
                    disabled={!canNext}
                    onClick={() => setOffset(eventsPage?.next_offset ?? offset)}
                  >
                    Next
                  </button>
                </div>
              </div>
              <p className="small text-muted mb-3">
                Showing events {offset + 1} to {(eventsPage?.events.length ?? 0) + offset}.
              </p>

              {!sessionId ? (
                <p className="small text-muted mb-0">Select a session to view replayable history.</p>
              ) : sessionLoading ? (
                <div className="small text-muted">Loading events...</div>
              ) : (
                <div className="timeline-list">
                  {(eventsPage?.events ?? []).map((event) => (
                    <article key={event.event_id} className="timeline-item mb-2">
                      <div className="d-flex justify-content-between align-items-center gap-2 mb-1">
                        <div className="d-flex align-items-center gap-2 flex-wrap">
                          <span className="badge bg-primary-subtle text-primary-emphasis">
                            {event.event_type}
                          </span>
                          <span className="badge bg-light text-dark border">{event.channel}</span>
                        </div>
                        <time className="small text-muted">{formatTimestamp(event.timestamp_utc)}</time>
                      </div>
                      <div className="small text-muted mb-2">
                        <strong>{event.actor_id}</strong> [{event.actor_role}] seq #{event.sequence}
                      </div>
                      <pre className="payload-view mb-0">{formatPayload(event.payload)}</pre>
                    </article>
                  ))}
                  {(eventsPage?.events.length ?? 0) === 0 ? (
                    <p className="small text-muted mb-0">No events available for this page.</p>
                  ) : null}
                </div>
              )}
            </div>
          </div>

          <div className="col-12 col-lg-3">
            <div className="surface-card p-3 h-100">
              <h2 className="h6 mb-2">Insights</h2>
              {!sessionId ? (
                <p className="small text-muted mb-0">Select a session to view details.</p>
              ) : (
                <>
                  <div className="mb-3">
                    <div className="d-flex justify-content-between">
                      <span className="small text-muted">Session</span>
                      <span className="small">{sessionId}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="small text-muted">Health</span>
                      <span className={`badge ${healthTone(currentHealth)}`}>
                        {currentHealth.toFixed(1)}
                      </span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="small text-muted">Events</span>
                      <span className="small">{summary?.count ?? 0}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="small text-muted">First</span>
                      <span className="small">{formatTimestamp(summary?.first_ts)}</span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="small text-muted">Last</span>
                      <span className="small">{formatTimestamp(summary?.last_ts)}</span>
                    </div>
                  </div>

                  <h3 className="h6 mb-2">Anomalies</h3>
                  <ul className="list-group list-group-flush mb-3">
                    {(analysis?.anomalies ?? []).length === 0 ? (
                      <li className="list-group-item px-0 py-1 small text-muted">None detected.</li>
                    ) : (
                      (analysis?.anomalies ?? []).map((item) => (
                        <li key={item.code} className="list-group-item px-0 py-1 small">
                          <strong>{item.code}</strong> [{item.severity}]
                        </li>
                      ))
                    )}
                  </ul>

                  <h3 className="h6 mb-2">Recommendations</h3>
                  <ul className="list-group list-group-flush mb-3">
                    {(analysis?.recommendations ?? []).map((item) => (
                      <li key={item} className="list-group-item px-0 py-1 small">
                        {item}
                      </li>
                    ))}
                  </ul>

                  <h3 className="h6 mb-2">Global Snapshot</h3>
                  <div className="small d-flex justify-content-between">
                    <span className="text-muted">Mean Health</span>
                    <span>{globalAnalysis?.mean_health_score ?? 0}</span>
                  </div>
                  <div className="small d-flex justify-content-between">
                    <span className="text-muted">Total Events</span>
                    <span>{globalAnalysis?.total_events ?? 0}</span>
                  </div>
                  <div className="small d-flex justify-content-between">
                    <span className="text-muted">Outliers</span>
                    <span>{globalAnalysis?.outlier_sessions.length ?? 0}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
