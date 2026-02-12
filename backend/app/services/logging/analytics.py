from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import log2
from statistics import fmean, pstdev
from typing import Any

from app.models.events import EventEnvelope


class ConversationAnalytics:
    """Advanced deterministic analytics for replayed conversation logs."""

    _KEYWORD_GROUPS = {
        "reliability": [
            "error",
            "exception",
            "fail",
            "failed",
            "timeout",
            "retry",
            "fallback",
            "missing",
            "invalid",
            "crash",
        ],
        "debate": [
            "disagree",
            "conflict",
            "counter",
            "challenge",
            "argue",
            "risk",
            "tradeoff",
            "compromise",
            "blocked",
        ],
        "decision": [
            "decide",
            "decision",
            "approved",
            "rejected",
            "selected",
            "deploy",
            "final",
            "resolved",
        ],
        "context": [
            "context",
            "handoff",
            "window",
            "summary",
            "resume",
            "continuity",
            "memory",
            "drift",
        ],
        "security": [
            "secret",
            "token",
            "auth",
            "redacted",
            "permission",
            "malicious",
            "access",
            "credential",
        ],
    }

    def analyze_session(
        self,
        *,
        session_id: str,
        events: list[EventEnvelope],
        bucket_seconds: int = 60,
        top_n: int = 10,
    ) -> dict[str, Any]:
        ordered = sorted(events, key=lambda item: (item.timestamp_utc, item.event_id))
        if not ordered:
            return {
                "session_id": session_id,
                "event_count": 0,
                "health_score": 0.0,
                "signals": {},
                "top_event_types": [],
                "top_actor_handoffs": [],
                "top_motifs_bigram": [],
                "top_motifs_trigram": [],
                "burst_windows": [],
                "anomalies": [],
                "recommendations": [
                    "No events found. Run workloads first, then re-run analysis.",
                ],
            }

        event_types = [event.event_type for event in ordered]
        actors = [event.actor_id for event in ordered]
        channels = [event.channel for event in ordered]
        latencies = [event.latency_ms for event in ordered]
        costs = [event.cost_usd for event in ordered]
        token_in_total = sum(event.token_in for event in ordered)
        token_out_total = sum(event.token_out for event in ordered)
        duration_seconds = self._duration_seconds(ordered)

        event_type_counts = Counter(event_types)
        actor_counts = Counter(actors)
        channel_counts = Counter(channels)
        handoffs = self._handoff_counts(actors)
        transitions = self._transition_counts(event_types)
        bigrams = self._motif_counts(event_types, size=2)
        trigrams = self._motif_counts(event_types, size=3)
        bursts = self._burst_windows(ordered, bucket_seconds=bucket_seconds)
        payload_signals = self._payload_signals(ordered)

        churn_ratio = self._churn_ratio(event_types)
        event_entropy = self._entropy(event_type_counts)
        actor_entropy = self._entropy(actor_counts)

        anomalies = self._detect_anomalies(
            duration_seconds=duration_seconds,
            event_count=len(ordered),
            churn_ratio=churn_ratio,
            bursts=bursts,
            signals=payload_signals,
            transitions=transitions,
            p95_latency=self._percentile(latencies, 95.0),
        )
        recommendations = self._recommendations(
            anomalies=anomalies,
            payload_signals=payload_signals,
            churn_ratio=churn_ratio,
            has_decisions=payload_signals["decision_hits"] > 0,
        )
        health_score = self._health_score(
            anomalies=anomalies,
            churn_ratio=churn_ratio,
            p95_latency=self._percentile(latencies, 95.0),
            decision_hits=payload_signals["decision_hits"],
            event_count=len(ordered),
        )

        return {
            "session_id": session_id,
            "event_count": len(ordered),
            "window": {
                "first_ts": ordered[0].timestamp_utc.isoformat(),
                "last_ts": ordered[-1].timestamp_utc.isoformat(),
                "duration_seconds": duration_seconds,
            },
            "resource_usage": {
                "token_in_total": token_in_total,
                "token_out_total": token_out_total,
                "cost_total_usd": round(sum(costs), 6),
                "latency_ms": {
                    "p50": round(self._percentile(latencies, 50.0), 3),
                    "p95": round(self._percentile(latencies, 95.0), 3),
                    "mean": round(fmean(latencies), 3) if latencies else 0.0,
                },
            },
            "distribution": {
                "event_type_entropy": round(event_entropy, 6),
                "actor_entropy": round(actor_entropy, 6),
                "channel_counts": dict(sorted(channel_counts.items())),
                "top_event_types": self._top_counter(event_type_counts, top_n=top_n),
                "top_actors": self._top_counter(actor_counts, top_n=top_n),
            },
            "interaction_graph": {
                "top_actor_handoffs": self._top_counter(handoffs, top_n=top_n),
                "transition_pairs": self._top_counter(transitions, top_n=top_n),
            },
            "pattern_mining": {
                "top_motifs_bigram": self._top_counter(bigrams, top_n=top_n),
                "top_motifs_trigram": self._top_counter(trigrams, top_n=top_n),
                "churn_ratio": round(churn_ratio, 6),
            },
            "signals": payload_signals,
            "burst_windows": bursts,
            "anomalies": anomalies,
            "recommendations": recommendations,
            "health_score": health_score,
        }

    def analyze_global(
        self,
        *,
        session_events: dict[str, list[EventEnvelope]],
        bucket_seconds: int = 60,
        top_n: int = 10,
    ) -> dict[str, Any]:
        analyses: dict[str, dict[str, Any]] = {}
        event_type_presence: Counter[str] = Counter()
        motif_presence: Counter[str] = Counter()
        health_pairs: list[tuple[str, float]] = []
        anomalies_by_session: dict[str, int] = {}

        for session_id, events in session_events.items():
            analysis = self.analyze_session(
                session_id=session_id,
                events=events,
                bucket_seconds=bucket_seconds,
                top_n=top_n,
            )
            analyses[session_id] = analysis
            health_pairs.append((session_id, float(analysis["health_score"])))
            anomalies_by_session[session_id] = len(analysis["anomalies"])

            for row in analysis["distribution"]["top_event_types"]:
                event_type_presence[row["key"]] += 1
            for row in analysis["pattern_mining"]["top_motifs_bigram"]:
                motif_presence[row["key"]] += 1

        recurring_event_types = [
            {"key": key, "sessions": count}
            for key, count in event_type_presence.most_common(top_n)
            if count > 1
        ]
        recurring_motifs = [
            {"key": key, "sessions": count}
            for key, count in motif_presence.most_common(top_n)
            if count > 1
        ]
        outliers = [
            {
                "session_id": session_id,
                "health_score": score,
                "anomaly_count": anomalies_by_session.get(session_id, 0),
            }
            for session_id, score in sorted(health_pairs, key=lambda item: item[1])[:top_n]
            if score < 70.0 or anomalies_by_session.get(session_id, 0) > 0
        ]

        total_events = sum(analysis["event_count"] for analysis in analyses.values())
        mean_health = (
            round(fmean(float(analysis["health_score"]) for analysis in analyses.values()), 4)
            if analyses
            else 0.0
        )

        return {
            "session_count": len(analyses),
            "total_events": total_events,
            "mean_health_score": mean_health,
            "recurring_event_types": recurring_event_types,
            "recurring_motifs_bigram": recurring_motifs,
            "outlier_sessions": outliers,
            "session_health": [{"session_id": sid, "health_score": score} for sid, score in health_pairs],
        }

    @staticmethod
    def _duration_seconds(events: list[EventEnvelope]) -> float:
        if len(events) <= 1:
            return 0.0
        return max(0.0, (events[-1].timestamp_utc - events[0].timestamp_utc).total_seconds())

    @staticmethod
    def _transition_counts(event_types: list[str]) -> Counter[str]:
        transition = Counter()
        for idx in range(1, len(event_types)):
            pair = f"{event_types[idx - 1]}->{event_types[idx]}"
            transition[pair] += 1
        return transition

    @staticmethod
    def _handoff_counts(actors: list[str]) -> Counter[str]:
        handoffs = Counter()
        for idx in range(1, len(actors)):
            if actors[idx] == actors[idx - 1]:
                continue
            pair = f"{actors[idx - 1]}->{actors[idx]}"
            handoffs[pair] += 1
        return handoffs

    @staticmethod
    def _motif_counts(event_types: list[str], *, size: int) -> Counter[str]:
        motifs = Counter()
        if len(event_types) < size:
            return motifs
        for idx in range(0, len(event_types) - size + 1):
            motif = " > ".join(event_types[idx : idx + size])
            motifs[motif] += 1
        return motifs

    def _payload_signals(self, events: list[EventEnvelope]) -> dict[str, int]:
        hit_counts = {f"{key}_hits": 0 for key in self._KEYWORD_GROUPS}
        total_tokens = 0
        for event in events:
            text = self._payload_text(event.payload)
            lowered = text.lower()
            total_tokens += len(lowered.split())
            for group, keywords in self._KEYWORD_GROUPS.items():
                hit_counts[f"{group}_hits"] += sum(lowered.count(keyword) for keyword in keywords)
        hit_counts["payload_token_estimate"] = total_tokens
        return hit_counts

    def _payload_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            chunks: list[str] = []
            for key, value in payload.items():
                chunks.append(str(key))
                chunks.append(self._payload_text(value))
            return " ".join(chunk for chunk in chunks if chunk)
        if isinstance(payload, list):
            return " ".join(self._payload_text(value) for value in payload)
        if isinstance(payload, str):
            return payload
        if payload is None:
            return ""
        return str(payload)

    @staticmethod
    def _churn_ratio(event_types: list[str]) -> float:
        if len(event_types) <= 1:
            return 0.0
        transitions = sum(1 for idx in range(1, len(event_types)) if event_types[idx] != event_types[idx - 1])
        return transitions / (len(event_types) - 1)

    @staticmethod
    def _entropy(counter: Counter[str]) -> float:
        total = sum(counter.values())
        if total <= 0:
            return 0.0
        entropy = 0.0
        for count in counter.values():
            probability = count / total
            entropy -= probability * log2(probability)
        return entropy

    @staticmethod
    def _percentile(values: list[int], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return float(ordered[0])
        rank = (len(ordered) - 1) * (pct / 100.0)
        low = int(rank)
        high = min(low + 1, len(ordered) - 1)
        fraction = rank - low
        return ordered[low] * (1.0 - fraction) + ordered[high] * fraction

    @staticmethod
    def _top_counter(counter: Counter[str], *, top_n: int) -> list[dict[str, Any]]:
        return [{"key": key, "count": count} for key, count in counter.most_common(top_n)]

    def _burst_windows(self, events: list[EventEnvelope], *, bucket_seconds: int) -> list[dict[str, Any]]:
        if len(events) <= 1 or bucket_seconds < 1:
            return []

        first = events[0].timestamp_utc
        buckets: defaultdict[int, int] = defaultdict(int)
        for event in events:
            delta = event.timestamp_utc - first
            index = int(delta.total_seconds() // bucket_seconds)
            buckets[index] += 1

        counts = list(buckets.values())
        if len(counts) <= 1:
            return []
        mean = fmean(counts)
        std = pstdev(counts) if len(counts) > 1 else 0.0
        threshold = mean + (2.0 * std)
        min_threshold = max(3.0, threshold)

        windows: list[dict[str, Any]] = []
        for index, count in sorted(buckets.items()):
            if count < min_threshold:
                continue
            start = first + timedelta(seconds=index * bucket_seconds)
            end = start + timedelta(seconds=bucket_seconds)
            windows.append(
                {
                    "bucket_index": index,
                    "start_ts": start.isoformat(),
                    "end_ts": end.isoformat(),
                    "event_count": count,
                    "z_score": round((count - mean) / std, 6) if std > 0 else 0.0,
                }
            )
        return windows

    def _detect_anomalies(
        self,
        *,
        duration_seconds: float,
        event_count: int,
        churn_ratio: float,
        bursts: list[dict[str, Any]],
        signals: dict[str, int],
        transitions: Counter[str],
        p95_latency: float,
    ) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        if event_count == 0:
            return anomalies

        reliability_density = signals["reliability_hits"] / max(event_count, 1)
        decision_density = signals["decision_hits"] / max(event_count, 1)
        debate_density = signals["debate_hits"] / max(event_count, 1)

        if reliability_density >= 0.2:
            anomalies.append(
                {
                    "code": "HIGH_RELIABILITY_SIGNAL_DENSITY",
                    "severity": "HIGH",
                    "value": round(reliability_density, 6),
                }
            )
        if debate_density > 0.2 and decision_density < 0.05:
            anomalies.append(
                {
                    "code": "DEBATE_WITHOUT_DECISIONS",
                    "severity": "MEDIUM",
                    "value": round(debate_density, 6),
                }
            )
        if bursts:
            anomalies.append(
                {
                    "code": "TEMPORAL_BURST_SPIKES",
                    "severity": "MEDIUM",
                    "value": len(bursts),
                }
            )
        if churn_ratio < 0.2 and duration_seconds > 60 and event_count > 20:
            anomalies.append(
                {
                    "code": "LOW_STATE_TRANSITION_CHURN",
                    "severity": "LOW",
                    "value": round(churn_ratio, 6),
                }
            )
        if p95_latency > 800:
            anomalies.append(
                {
                    "code": "HIGH_P95_LATENCY",
                    "severity": "MEDIUM",
                    "value": round(p95_latency, 3),
                }
            )

        oscillation_pairs = self._oscillation_pairs(transitions)
        if oscillation_pairs:
            anomalies.append(
                {
                    "code": "OSCILLATION_LOOP_PATTERN",
                    "severity": "MEDIUM",
                    "pairs": oscillation_pairs,
                }
            )
        return anomalies

    @staticmethod
    def _oscillation_pairs(transitions: Counter[str]) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for key, count in transitions.items():
            if "->" not in key:
                continue
            left, right = key.split("->", 1)
            if (left, right) in seen or left == right:
                continue
            reverse_key = f"{right}->{left}"
            reverse_count = transitions.get(reverse_key, 0)
            if count >= 2 and reverse_count >= 2:
                pairs.append({"pair": f"{left}<->{right}", "count_forward": count, "count_reverse": reverse_count})
            seen.add((left, right))
            seen.add((right, left))
        return pairs

    @staticmethod
    def _recommendations(
        *,
        anomalies: list[dict[str, Any]],
        payload_signals: dict[str, int],
        churn_ratio: float,
        has_decisions: bool,
    ) -> list[str]:
        recommendations: list[str] = []
        codes = {item["code"] for item in anomalies}

        if "HIGH_RELIABILITY_SIGNAL_DENSITY" in codes:
            recommendations.append(
                "Enable correction-agent automation for this session and require remediation checkpoints."
            )
        if "DEBATE_WITHOUT_DECISIONS" in codes:
            recommendations.append(
                "Inject decision-deadline prompts to convert debate cycles into explicit approvals/rejections."
            )
        if "TEMPORAL_BURST_SPIKES" in codes:
            recommendations.append(
                "Apply burst-aware summarization every spike window to reduce context overload."
            )
        if "OSCILLATION_LOOP_PATTERN" in codes:
            recommendations.append(
                "Trigger tie-break arbitration to break oscillation loops between repeated event transitions."
            )
        if payload_signals.get("context_hits", 0) > payload_signals.get("decision_hits", 0) * 2:
            recommendations.append(
                "Context-management chatter is high relative to outcomes; prioritize action cards with completion checks."
            )
        if churn_ratio < 0.25 and has_decisions:
            recommendations.append(
                "Session is stable; snapshot this flow as a reusable playbook template."
            )
        if not recommendations:
            recommendations.append("No urgent anomalies detected. Keep current workflow and monitor trend deltas.")
        return recommendations

    @staticmethod
    def _health_score(
        *,
        anomalies: list[dict[str, Any]],
        churn_ratio: float,
        p95_latency: float,
        decision_hits: int,
        event_count: int,
    ) -> float:
        score = 100.0
        severity_penalty = {"LOW": 4.0, "MEDIUM": 8.0, "HIGH": 15.0}
        for anomaly in anomalies:
            score -= severity_penalty.get(str(anomaly.get("severity", "LOW")), 4.0)
        if p95_latency > 800:
            score -= min(12.0, (p95_latency - 800) / 200.0)
        if churn_ratio < 0.15 and event_count > 20:
            score -= 6.0
        if decision_hits == 0 and event_count > 10:
            score -= 10.0
        return round(max(0.0, min(score, 100.0)), 2)
