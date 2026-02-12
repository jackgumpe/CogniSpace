# Context Window Transition Research v1

Status: Approved
Date: 2026-02-10
Owner: Project

## Objective
Define a reliable method to transition an agent from one context window to the next without semantic drift, silent failure, or loss of critical state.

## Source Set
- `research/HCM/HCM-Integration-Feasibility.docx`
- `research/HCM/context-aware-hierarchical.pdf`
- `research/HCM/context-merging.pdf`
- `research/HCM/Hierarchical_context_pruning.pdf`
- `research/Long-context/Helmet-evaluate-long-context.pdf`
- `research/Long-context/Recursive-large-models.pdf`
- Protocol artifact: `docs/protocols/context-window-transition.v1.json`

## Research Conclusions
- Naive long-context accumulation degrades reasoning quality as length grows.
- Recursive and externalized-memory methods scale better than single-window linear prompts.
- Evidence-grounded handoff (support/refine) is safer than summary-only carryover.
- For code tasks, topology-aware pruning is preferred over flat retrieval.
- Evaluation must include diverse categories; synthetic-only tests are insufficient.

## Adopted Protocol
The project adopts:
- `CONTEXT_WINDOW_TRANSITION_V1` in `docs/protocols/context-window-transition.v1.json`

It defines:
- Trigger policy for handoff initiation.
- Required handoff packet schema.
- Transition algorithm (freeze, snapshot, compress, prune, validate, bootstrap, verify).
- Continuity probes for mission/threads/decisions/artifacts/risks.
- Hard failure criteria and fallback actions.
- Required observability events and metrics.

## Implementation Requirements
1. Add handoff event types:
- `CONTEXT_HANDOFF_STARTED`
- `CONTEXT_HANDOFF_PACKET_BUILT`
- `CONTEXT_HANDOFF_VALIDATED`
- `CONTEXT_HANDOFF_BOOTSTRAPPED`
- `CONTEXT_HANDOFF_FAILED`
- `CONTEXT_HANDOFF_COMPLETED`

2. Persist handoff packet:
- First event in next context window.
- Schema validation required before execution.

3. Add continuity verification:
- Probe endpoint or service call before agent resumes work.
- Block resume on failed probes.

4. Integrate with dataset pipeline:
- Include handoff packet and continuity outcomes in JSONIC exports.
- Keep raw access opt-in and controlled.

## Quality Gates
All gates are mandatory:
- `invariants_passed == true`
- `coverage_score >= 0.80`
- `confidence_score >= 0.80`
- `continuity_probe_pass_rate == 1.0`
- No increase in silent failures after rollout.

## Rollout Plan
1. Implement handoff packet write/read and validation.
2. Add continuity probes and failure blocking.
3. Add replay and dataset coverage for handoff events.
4. Run offline and online gate checks.
5. Promote only after all gates pass.

## Risk Controls
- Reject handoff if constraints are missing.
- Retry with larger evidence budget if coverage is low.
- Trigger system alert and block execution on repeated handoff failure.
- Keep sanitized logs default; raw logs restricted to controlled dataset builds.
