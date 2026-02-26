from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from app.models.gitops import (
    GitAdviceRequest,
    GitAdviceResponse,
    GitAgentRecommendation,
    GitBootstrapConfig,
    GitExecutionStep,
    GitHandoffRequest,
    GitHandoffResponse,
    GitMetaPlanMetric,
    GitMetaPlanRequest,
    GitMetaPlanResponse,
    GitMetaSquaredAssessment,
    GitMetaSquaredThresholdUpdate,
    GitRepoSnapshot,
)


@dataclass(slots=True)
class _PathspecScopeStatus:
    return_code: int
    command: str
    stdout: str
    stderr: str
    changed_paths: list[str]


class GitOpsAdvisor:
    """Deterministic git workflow advisor with multi-agent style recommendations."""

    _BRANCH_TRACK_RE = re.compile(r"\[(?P<tracking>.+?)\]")
    _AHEAD_RE = re.compile(r"ahead\s+(?P<count>\d+)")
    _BEHIND_RE = re.compile(r"behind\s+(?P<count>\d+)")
    _DEFAULT_PROTECTED_BRANCHES = {"main", "master"}
    _STALE_DAYS = 30

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]

    def snapshot(self) -> GitRepoSnapshot:
        inside = self._run_git(["rev-parse", "--is-inside-work-tree"])
        if inside[0] != 0 or inside[1].strip().lower() != "true":
            warning = inside[2].strip() or "Not inside a git worktree."
            return GitRepoSnapshot(
                status="UNAVAILABLE",
                repo_root=str(self.repo_root),
                current_branch="UNKNOWN",
                warnings=[warning],
            )

        current_branch = self._git_or("symbolic-ref", "--short", "HEAD", default="")
        if not current_branch:
            current_branch = self._git_or("rev-parse", "--abbrev-ref", "HEAD", default="UNKNOWN")
        status_porcelain = self._git_or(
            "status",
            "--porcelain",
            "--branch",
            "--untracked-files=all",
            default="",
        )
        staged, modified, untracked, ahead, behind, changed_paths = self._parse_porcelain_status(
            status_porcelain
        )

        remote_name, remote_url = self._primary_remote()
        stale, merged = self._branch_hygiene()
        warnings: list[str] = []
        if current_branch in self._DEFAULT_PROTECTED_BRANCHES and (staged + modified + untracked) > 0:
            warnings.append("Direct work on protected branch detected; create feature branch before committing.")
        if remote_name is None:
            warnings.append("No git remote configured.")

        return GitRepoSnapshot(
            status="OK",
            repo_root=str(self.repo_root),
            current_branch=current_branch,
            remote_name=remote_name,
            remote_url=remote_url,
            is_github_remote=bool(remote_url and "github.com" in remote_url.lower()),
            is_detached_head=current_branch == "HEAD",
            staged_files=staged,
            modified_files=modified,
            untracked_files=untracked,
            total_changed_files=staged + modified + untracked,
            ahead_count=ahead,
            behind_count=behind,
            stale_local_branches=stale,
            merged_local_branches=merged,
            changed_paths=changed_paths,
            warnings=warnings,
        )

    def advise(self, request: GitAdviceRequest) -> GitAdviceResponse:
        snapshot = self.snapshot()
        session_id = request.session_id or f"sess_git_{uuid4().hex[:10]}"
        trace_id = request.trace_id or f"trace_git_{uuid4().hex[:10]}"

        recommendations = [
            self._branch_strategist(snapshot=snapshot, request=request),
            self._commit_auditor(snapshot=snapshot, request=request),
            self._hygiene_keeper(snapshot=snapshot, request=request),
        ]
        should_fork = recommendations[0].primary_action == "FORK_OR_BRANCH"
        should_prune = recommendations[2].primary_action == "PRUNE"
        commit_message = self._suggest_commit_message(request=request)
        pr_comment = self._suggest_pr_comment(request=request, snapshot=snapshot)
        consolidated_actions = self._consolidate(recommendations=recommendations, snapshot=snapshot)
        bootstrap_commands = self._bootstrap_commands(request=request, snapshot=snapshot)

        return GitAdviceResponse(
            advice_id=f"gitadv_{uuid4().hex[:12]}",
            objective=request.objective,
            repo_snapshot=snapshot,
            agent_recommendations=recommendations,
            consolidated_actions=consolidated_actions,
            suggested_commit_message=commit_message,
            suggested_pr_comment=pr_comment,
            should_fork=should_fork,
            should_prune=should_prune,
            bootstrap_commands=bootstrap_commands,
            session_id=session_id,
            trace_id=trace_id,
        )

    def meta_plan(self, request: GitMetaPlanRequest) -> GitMetaPlanResponse:
        snapshot = self.snapshot()
        session_id = request.session_id or f"sess_git_meta_{uuid4().hex[:10]}"
        trace_id = request.trace_id or f"trace_git_meta_{uuid4().hex[:10]}"
        advice = self.advise(
            GitAdviceRequest(
                objective=request.objective,
                changes_summary="Meta planning for git automation and perpetual quality loop.",
                risk_level=request.risk_level,
                collaboration_mode="TEAM",
                include_bootstrap_plan=True,
                repo_name=request.repo_name,
                session_id=session_id,
                trace_id=trace_id,
            )
        )
        specialist_team = advice.agent_recommendations + [
            GitAgentRecommendation(
                agent_id="git_agent_meta",
                focus="meta_planning",
                confidence=0.86,
                primary_action="NOOP",
                rationale=(
                    "Maintain meta metrics, detect planning drift, and trigger autoprompt tuning "
                    "when thresholds regress."
                ),
                commands=[
                    "gitops meta-plan --objective \"...\" --output-json",
                    "autoprompt metrics score-preview --task-key git_meta --prompt \"...\" --output-json",
                ],
            )
        ]
        metrics = self._meta_metrics()
        meta_squared = self._meta_squared_assessment(
            snapshot=snapshot,
            request=request,
            metrics=metrics,
        )
        return GitMetaPlanResponse(
            plan_id=f"gitmeta_{uuid4().hex[:12]}",
            objective=request.objective,
            repo_snapshot=snapshot,
            specialist_team=specialist_team,
            meta_metrics=metrics,
            autoprompt_tracks=[
                "plan_autoprompt: optimize branch/commit/PR strategy wording for low ambiguity.",
                "impl_autoprompt: generate execution checklist before each git operation burst.",
                "post_impl_autoprompt: score commit quality and rollback confidence after each merge.",
            ],
            update_loop=[
                "Every PR: recompute meta metrics and append result to planning log.",
                "If any metric crosses critical threshold: open hard-stop card and require lead approval.",
                "If three consecutive windows are stable: tighten thresholds by 5% for continuous improvement.",
            ],
            fork_policy=[
                "Fork/branch when working directly on protected branch with local changes.",
                "Fork/branch when ahead_count >= 8 to reduce review risk.",
                "Fork/branch when conflict density exceeds threshold in two consecutive windows.",
            ],
            prune_policy=[
                "Prune merged branches weekly.",
                "Prune stale branches older than 30 days unless tagged as long_horizon.",
                "Run remote prune after branch cleanup to keep topology accurate.",
            ],
            merge_policy=[
                "Merge only when replayable checks and contract checks are green.",
                "Require PR notes to include risk, rollback path, and metric deltas.",
                "Block merge on meta drift critical threshold breaches.",
            ],
            baseline_targets=self._baseline_targets(metrics=metrics),
            meta_squared=meta_squared,
            session_id=session_id,
            trace_id=trace_id,
        )

    def handoff(self, request: GitHandoffRequest) -> GitHandoffResponse:
        session_id = request.session_id or f"sess_git_handoff_{uuid4().hex[:10]}"
        trace_id = request.trace_id or f"trace_git_handoff_{uuid4().hex[:10]}"
        before = self.snapshot()
        meta_plan = self.meta_plan(
            GitMetaPlanRequest(
                objective=request.objective,
                repo_name=request.repo_name,
                risk_level=request.risk_level,
                include_hf_scan=True,
                meta_squared_mode=request.meta_squared_mode,
                session_id=session_id,
                trace_id=trace_id,
            )
        )
        branch_name = f"feature/{self._slugify(request.objective)}"
        pathspec, invalid_pathspec = self._normalize_pathspec(request.pathspec)
        steps: list[GitExecutionStep] = []
        execute = not request.dry_run

        if before.status != "OK":
            steps.append(
                GitExecutionStep(
                    step_id="validate_repo",
                    description="Validate repository accessibility.",
                    command="git rev-parse --is-inside-work-tree",
                    status="FAILED" if execute else "PLANNED",
                    return_code=1 if execute else None,
                    stderr_excerpt="Repository unavailable or not a git worktree.",
                )
            )
            return self._handoff_response(
                objective=request.objective,
                dry_run=request.dry_run,
                branch_name=branch_name,
                pathspec=pathspec,
                before=before,
                after=self.snapshot(),
                meta_plan=meta_plan,
                steps=steps,
                session_id=session_id,
                trace_id=trace_id,
            )

        if invalid_pathspec:
            steps.append(
                GitExecutionStep(
                    step_id="validate_pathspec",
                    description=f"Invalid pathspec entries: {', '.join(invalid_pathspec)}",
                    status="FAILED" if execute else "PLANNED",
                    stderr_excerpt="Pathspec entries must be repo-relative and cannot include '..' segments.",
                )
            )
            if execute:
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )

        if before.current_branch in self._DEFAULT_PROTECTED_BRANCHES and before.total_changed_files > 0 and not pathspec:
            steps.append(
                GitExecutionStep(
                    step_id="safety_guard",
                    description="Protected branch has local changes; provide --pathspec for scoped execute.",
                    status="FAILED" if execute else "PLANNED",
                    stderr_excerpt="Execute mode blocked without pathspec on protected dirty branch.",
                )
            )
            if execute:
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )

        should_branch = before.current_branch in self._DEFAULT_PROTECTED_BRANCHES and before.total_changed_files > 0
        if should_branch:
            steps.append(
                self._run_step(
                    step_id="create_feature_branch",
                    description="Create feature branch from protected branch before modifications.",
                    command=["git", "checkout", "-b", branch_name],
                    dry_run=request.dry_run,
                )
            )
            if execute and steps[-1].status == "FAILED":
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="create_feature_branch",
                    description="Feature branch creation not required by policy.",
                    status="SKIPPED",
                )
            )

        if request.run_tests:
            test_command = self._parse_test_command(request.test_command)
            steps.append(
                self._run_step(
                    step_id="run_tests",
                    description="Run regression test pack before commit/push.",
                    command=test_command,
                    dry_run=request.dry_run,
                )
            )
            if execute and steps[-1].status == "FAILED":
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="run_tests",
                    description="Pre-commit test run disabled by request.",
                    status="SKIPPED",
                )
            )

        snapshot_for_commit = self.snapshot()
        scoped_changed_paths: list[str] = []
        if pathspec:
            scope_status = self._scoped_changes_for_pathspec(pathspec)
            if scope_status.return_code != 0:
                steps.append(
                    GitExecutionStep(
                        step_id="resolve_pathspec",
                        description="Resolve changed files for provided pathspec.",
                        command=scope_status.command,
                        status="FAILED" if execute else "PLANNED",
                        return_code=scope_status.return_code if execute else None,
                        stdout_excerpt=self._clip(scope_status.stdout),
                        stderr_excerpt=self._clip(scope_status.stderr),
                    )
                )
                if execute:
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
            else:
                scoped_changed_paths = scope_status.changed_paths

        has_changes_for_commit = bool(scoped_changed_paths) if pathspec else snapshot_for_commit.total_changed_files > 0
        if has_changes_for_commit:
            stage_command = ["git", "add", "--", *pathspec] if pathspec else ["git", "add", "-A"]
            stage_description = (
                "Stage pathspec-scoped modified files."
                if pathspec
                else "Stage all modified files."
            )
            steps.append(
                self._run_step(
                    step_id="stage_changes",
                    description=stage_description,
                    command=stage_command,
                    dry_run=request.dry_run,
                )
            )
            if execute and steps[-1].status == "FAILED":
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )

            commit_message = self._suggest_commit_message(
                request=GitAdviceRequest(
                    objective=request.objective,
                    risk_level=request.risk_level,
                    repo_name=request.repo_name,
                )
            )
            steps.append(
                self._run_step(
                    step_id="commit_changes",
                    description="Create commit for handoff automation batch.",
                    command=["git", "commit", "-m", commit_message],
                    dry_run=request.dry_run,
                )
            )
            if execute and steps[-1].status == "FAILED":
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )
        else:
            skipped_stage_reason = (
                "No changed files detected for provided pathspec; staging skipped."
                if pathspec
                else "No changed files detected; staging skipped."
            )
            skipped_commit_reason = (
                "No changed files detected for provided pathspec; commit skipped."
                if pathspec
                else "No changed files detected; commit skipped."
            )
            steps.append(
                GitExecutionStep(
                    step_id="stage_changes",
                    description=skipped_stage_reason,
                    status="SKIPPED",
                )
            )
            steps.append(
                GitExecutionStep(
                    step_id="commit_changes",
                    description=skipped_commit_reason,
                    status="SKIPPED",
                )
            )

        push_branch_name = branch_name if should_branch else before.current_branch
        if request.push_branch:
            remote_name = before.remote_name or "origin"
            if before.remote_name is None:
                steps.append(
                    GitExecutionStep(
                        step_id="push_branch",
                        description="No remote configured; push skipped.",
                        status="SKIPPED",
                    )
                )
            else:
                steps.append(
                    self._run_step(
                        step_id="push_branch",
                        description="Push branch to remote.",
                        command=["git", "push", "-u", remote_name, push_branch_name],
                        dry_run=request.dry_run,
                    )
                )
                if execute and steps[-1].status == "FAILED":
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=push_branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="push_branch",
                    description="Push disabled by request.",
                    status="SKIPPED",
                )
            )

        if request.create_pr:
            steps.append(
                self._run_step(
                    step_id="create_pr",
                    description="Open pull request with generated summary.",
                    command=["gh", "pr", "create", "--fill"],
                    dry_run=request.dry_run,
                    requires_tool="gh",
                )
            )
            if execute and steps[-1].status == "FAILED":
                return self._handoff_response(
                    objective=request.objective,
                    dry_run=request.dry_run,
                    branch_name=push_branch_name,
                    pathspec=pathspec,
                    before=before,
                    after=self.snapshot(),
                    meta_plan=meta_plan,
                    steps=steps,
                    session_id=session_id,
                    trace_id=trace_id,
                )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="create_pr",
                    description="PR creation disabled by request.",
                    status="SKIPPED",
                )
            )

        if request.include_bootstrap:
            bootstrap_cfg = request.bootstrap or GitBootstrapConfig()
            missing = self._missing_bootstrap_fields(bootstrap_cfg)
            if missing:
                steps.append(
                    GitExecutionStep(
                        step_id="bootstrap_azure",
                        description=f"Bootstrap config missing required fields: {', '.join(missing)}",
                        status="FAILED" if execute else "PLANNED",
                        stderr_excerpt="Provide bootstrap.repo and bootstrap.resource_group.",
                    )
                )
                if execute:
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=push_branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
            else:
                steps.append(
                    self._run_step(
                        step_id="bootstrap_azure",
                        description="Bootstrap Azure infra and wire GitHub secrets.",
                        command=self._bootstrap_command(bootstrap_cfg),
                        dry_run=request.dry_run,
                        requires_tool="powershell.exe",
                    )
                )
                if execute and steps[-1].status == "FAILED":
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=push_branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="bootstrap_azure",
                    description="Azure bootstrap disabled by request.",
                    status="SKIPPED",
                )
            )

        if request.trigger_workflows:
            bootstrap_cfg = request.bootstrap or GitBootstrapConfig()
            repo_slug = bootstrap_cfg.repo
            if not repo_slug:
                steps.append(
                    GitExecutionStep(
                        step_id="trigger_workflows",
                        description="Workflow trigger skipped: bootstrap.repo is required.",
                        status="FAILED" if execute else "PLANNED",
                        stderr_excerpt="Set bootstrap.repo to owner/name.",
                    )
                )
            else:
                steps.append(
                    self._run_step(
                        step_id="trigger_backend_workflow",
                        description="Trigger backend deployment workflow.",
                        command=["gh", "workflow", "run", "deploy-backend-azure.yml", "--repo", repo_slug],
                        dry_run=request.dry_run,
                        requires_tool="gh",
                    )
                )
                if execute and steps[-1].status == "FAILED":
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=push_branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
                steps.append(
                    self._run_step(
                        step_id="trigger_frontend_workflow",
                        description="Trigger frontend deployment workflow.",
                        command=["gh", "workflow", "run", "deploy-frontend-azure.yml", "--repo", repo_slug],
                        dry_run=request.dry_run,
                        requires_tool="gh",
                    )
                )
                if execute and steps[-1].status == "FAILED":
                    return self._handoff_response(
                        objective=request.objective,
                        dry_run=request.dry_run,
                        branch_name=push_branch_name,
                        pathspec=pathspec,
                        before=before,
                        after=self.snapshot(),
                        meta_plan=meta_plan,
                        steps=steps,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
        else:
            steps.append(
                GitExecutionStep(
                    step_id="trigger_workflows",
                    description="Workflow triggering disabled by request.",
                    status="SKIPPED",
                )
            )

        return self._handoff_response(
            objective=request.objective,
            dry_run=request.dry_run,
            branch_name=push_branch_name,
            pathspec=pathspec,
            before=before,
            after=self.snapshot(),
            meta_plan=meta_plan,
            steps=steps,
            session_id=session_id,
            trace_id=trace_id,
        )

    def _branch_strategist(
        self,
        *,
        snapshot: GitRepoSnapshot,
        request: GitAdviceRequest,
    ) -> GitAgentRecommendation:
        if snapshot.status != "OK":
            return GitAgentRecommendation(
                agent_id="git_agent_topology",
                focus="branch_topology",
                confidence=0.55,
                primary_action="FORK_OR_BRANCH",
                rationale="Repository snapshot unavailable; bootstrap or attach repository first.",
                commands=self._bootstrap_commands(request=request, snapshot=snapshot),
            )

        commands: list[str] = []
        action: str = "NOOP"
        rationale = "Current branch topology is acceptable."
        confidence = 0.74
        slug = self._slugify(request.objective)
        feature_branch = f"feature/{slug}"

        if snapshot.current_branch in self._DEFAULT_PROTECTED_BRANCHES and snapshot.total_changed_files > 0:
            action = "FORK_OR_BRANCH"
            rationale = "Work is happening directly on protected branch; isolate changes in a feature branch."
            commands.extend(
                [
                    f"git checkout -b {feature_branch}",
                    f"git switch {feature_branch}",
                ]
            )
            confidence = 0.93
        elif snapshot.remote_name is None:
            action = "FORK_OR_BRANCH"
            rationale = "No remote configured; connect to GitHub before collaboration."
            commands.extend(self._bootstrap_commands(request=request, snapshot=snapshot))
            confidence = 0.88
        elif snapshot.behind_count > 0:
            action = "SYNC"
            rationale = "Local branch is behind upstream; rebase before adding new commits."
            commands.append(f"git pull --rebase {snapshot.remote_name} {snapshot.current_branch}")
            confidence = 0.81
        elif snapshot.ahead_count >= 8:
            action = "FORK_OR_BRANCH"
            rationale = "Large ahead delta suggests opening a PR now to reduce review risk."
            commands.append("git push")
            commands.append("gh pr create --fill")
            confidence = 0.79

        return GitAgentRecommendation(
            agent_id="git_agent_topology",
            focus="branch_topology",
            confidence=confidence,
            primary_action=action,  # type: ignore[arg-type]
            rationale=rationale,
            commands=commands,
        )

    def _commit_auditor(
        self,
        *,
        snapshot: GitRepoSnapshot,
        request: GitAdviceRequest,
    ) -> GitAgentRecommendation:
        if snapshot.total_changed_files == 0:
            return GitAgentRecommendation(
                agent_id="git_agent_commit",
                focus="commit_strategy",
                confidence=0.9,
                primary_action="NOOP",
                rationale="No changes detected; commit is not required.",
                commands=[],
            )

        commit_message = self._suggest_commit_message(request=request)
        commands = ["git add -A", f'git commit -m "{commit_message}"']
        rationale = "Bundle related files into one coherent commit with explicit scope."
        confidence = 0.8

        if snapshot.total_changed_files > 10:
            rationale = "Change-set is large; split into 2-3 scoped commits for safer rollback."
            commands = [
                "git add <scope1_paths>",
                f'git commit -m "{commit_message}"',
                "git add <scope2_paths>",
                'git commit -m "test: add regression checks for gitops flow"',
            ]
            confidence = 0.87

        return GitAgentRecommendation(
            agent_id="git_agent_commit",
            focus="commit_strategy",
            confidence=confidence,
            primary_action="COMMIT",
            rationale=rationale,
            commands=commands,
        )

    def _hygiene_keeper(
        self,
        *,
        snapshot: GitRepoSnapshot,
        request: GitAdviceRequest,
    ) -> GitAgentRecommendation:
        del request
        stale = snapshot.stale_local_branches
        merged = snapshot.merged_local_branches
        commands: list[str] = []

        if stale or merged:
            for branch in (stale + merged)[:8]:
                if branch in self._DEFAULT_PROTECTED_BRANCHES:
                    continue
                commands.append(f"git branch -d {branch}")
            commands.append("git remote prune origin")
            return GitAgentRecommendation(
                agent_id="git_agent_hygiene",
                focus="branch_hygiene",
                confidence=0.82,
                primary_action="PRUNE",
                rationale=(
                    f"Detected {len(stale)} stale and {len(merged)} merged branches; prune to reduce branch noise."
                ),
                commands=commands,
            )

        if snapshot.behind_count > 0:
            return GitAgentRecommendation(
                agent_id="git_agent_hygiene",
                focus="branch_hygiene",
                confidence=0.76,
                primary_action="SYNC",
                rationale="Sync upstream before additional development to avoid merge friction.",
                commands=[f"git pull --rebase {snapshot.remote_name or 'origin'} {snapshot.current_branch}"],
            )

        return GitAgentRecommendation(
            agent_id="git_agent_hygiene",
            focus="branch_hygiene",
            confidence=0.7,
            primary_action="NOOP",
            rationale="No prune or sync actions required right now.",
            commands=[],
        )

    def _bootstrap_commands(self, *, request: GitAdviceRequest, snapshot: GitRepoSnapshot) -> list[str]:
        if not request.include_bootstrap_plan and snapshot.remote_name is not None:
            return []

        remote_url = request.remote_url or "<github_repo_url>"
        repo_name = request.repo_name.strip() or "CogniSpace"
        return [
            f"# bootstrap target: {repo_name}",
            "git init",
            "git branch -M main",
            f"git remote add origin {remote_url}",
            "git add .",
            f'git commit -m "chore: initialize {repo_name} workspace"',
            "git push -u origin main",
        ]

    @staticmethod
    def _suggest_commit_message(*, request: GitAdviceRequest) -> str:
        objective = request.objective.strip()
        lower = objective.lower()
        prefix = "feat"
        if any(token in lower for token in ("fix", "bug", "error", "failure")):
            prefix = "fix"
        elif any(token in lower for token in ("refactor", "cleanup")):
            prefix = "refactor"
        elif any(token in lower for token in ("test", "qa", "coverage")):
            prefix = "test"
        scope = GitOpsAdvisor._slugify(objective.split()[0] if objective.split() else "core")
        summary = " ".join(objective.split()[:10])
        return f"{prefix}({scope}): {summary}"

    @staticmethod
    def _suggest_pr_comment(*, request: GitAdviceRequest, snapshot: GitRepoSnapshot) -> str:
        summary = request.changes_summary or "No extra summary supplied."
        return (
            f"Objective: {request.objective}\n"
            f"Risk level: {request.risk_level}\n"
            f"Branch: {snapshot.current_branch}\n"
            f"Changed files: {snapshot.total_changed_files}\n"
            f"Summary: {summary}\n"
            "Review ask: verify budgets, logging determinism, and context-handoff checks."
        )

    @staticmethod
    def _consolidate(
        *,
        recommendations: list[GitAgentRecommendation],
        snapshot: GitRepoSnapshot,
    ) -> list[str]:
        actions: list[str] = []
        if snapshot.status != "OK":
            actions.append("Repository unavailable. Run bootstrap steps before development.")
            return actions
        for row in recommendations:
            if row.rationale not in actions:
                actions.append(row.rationale)
        if snapshot.total_changed_files == 0:
            actions.append("No local file changes detected. Skip commit and continue planning.")
        return actions

    @staticmethod
    def _meta_metrics() -> list[GitMetaPlanMetric]:
        return [
            GitMetaPlanMetric(
                metric_id="planning_drift_rate",
                layer="PLAN",
                definition=(
                    "Fraction of cards changed after scope freeze. Captures instability in planning intent."
                ),
                signal_source="kanban_plan_deltas",
                cadence="per_pr",
                direction="LOWER_IS_BETTER",
                warn_threshold=0.25,
                critical_threshold=0.4,
            ),
            GitMetaPlanMetric(
                metric_id="automation_coverage",
                layer="IMPLEMENTATION",
                definition=(
                    "Share of git workflow steps executed through scripted or CLI automation."
                ),
                signal_source="cli_command_audit",
                cadence="daily",
                direction="HIGHER_IS_BETTER",
                warn_threshold=0.7,
                critical_threshold=0.5,
            ),
            GitMetaPlanMetric(
                metric_id="merge_rework_rate",
                layer="POST_IMPLEMENTATION",
                definition=(
                    "Commits requiring follow-up fix within 48h after merge."
                ),
                signal_source="post_merge_fix_commits",
                cadence="daily",
                direction="LOWER_IS_BETTER",
                warn_threshold=0.2,
                critical_threshold=0.35,
            ),
            GitMetaPlanMetric(
                metric_id="team_decision_latency_minutes",
                layer="TEAM",
                definition=(
                    "Median minutes from conflict detection to supervisor/lead decision."
                ),
                signal_source="debate_and_decision_events",
                cadence="per_pr",
                direction="LOWER_IS_BETTER",
                warn_threshold=90.0,
                critical_threshold=180.0,
            ),
            GitMetaPlanMetric(
                metric_id="code_style_entropy",
                layer="POST_IMPLEMENTATION",
                definition=(
                    "Approximate style divergence score to catch swiss-cheese/frankenstein code patterns."
                ),
                signal_source="lint_and_diff_style_scan",
                cadence="per_pr",
                direction="LOWER_IS_BETTER",
                warn_threshold=0.35,
                critical_threshold=0.55,
            ),
        ]

    @staticmethod
    def _baseline_targets(*, metrics: list[GitMetaPlanMetric]) -> dict[str, float]:
        return {row.metric_id: row.warn_threshold for row in metrics}

    def _meta_squared_assessment(
        self,
        *,
        snapshot: GitRepoSnapshot,
        request: GitMetaPlanRequest,
        metrics: list[GitMetaPlanMetric],
    ) -> GitMetaSquaredAssessment:
        if request.meta_squared_mode == "OFF":
            return GitMetaSquaredAssessment(
                mode="OFF",
                enabled=False,
                triggered=False,
                recommendations=[
                    "Meta-squared disabled. Use PATCH mode for due-diligence checks on risky changes."
                ],
            )

        triggers: list[str] = []
        if snapshot.total_changed_files >= 12:
            triggers.append("changed_files_gte_12")
        if request.risk_level == "HIGH":
            triggers.append("risk_level_high")
        if self._touches_sensitive_paths(snapshot.changed_paths):
            triggers.append("touches_sensitive_paths")

        triggered = len(triggers) > 0
        if not triggered:
            return GitMetaSquaredAssessment(
                mode="PATCH",
                enabled=True,
                triggered=False,
                trigger_reasons=[],
                metric_quality_score=0.72,
                threshold_fitness_score=0.74,
                decision_alignment_score=0.7,
                recommendations=[
                    "No patch-level trigger active. Continue standard meta metrics and review at PR boundary."
                ],
            )

        churn = min(snapshot.total_changed_files / 80.0, 1.0)
        risk_penalty = 0.16 if request.risk_level == "HIGH" else (0.08 if request.risk_level == "MEDIUM" else 0.04)
        protected_branch_penalty = 0.08 if (
            snapshot.current_branch in self._DEFAULT_PROTECTED_BRANCHES and snapshot.total_changed_files > 0
        ) else 0.0
        metric_quality_score = max(0.0, min(1.0, 0.88 - (churn * 0.22) - risk_penalty))
        threshold_fitness_score = max(
            0.0,
            min(1.0, 0.84 - (churn * 0.18) - protected_branch_penalty),
        )
        decision_alignment_score = max(
            0.0,
            min(1.0, 0.82 - (churn * 0.14) - (0.1 if snapshot.behind_count > 0 else 0.0)),
        )
        updates = self._bounded_threshold_updates(metrics=metrics, churn=churn, high_risk=request.risk_level == "HIGH")

        return GitMetaSquaredAssessment(
            mode="PATCH",
            enabled=True,
            triggered=True,
            trigger_reasons=triggers,
            metric_quality_score=round(metric_quality_score, 4),
            threshold_fitness_score=round(threshold_fitness_score, 4),
            decision_alignment_score=round(decision_alignment_score, 4),
            bounded_threshold_updates=updates,
            recommendations=[
                "Require lead/supervisor review before accepting threshold updates.",
                "Do not auto-merge based on meta-squared score only.",
                "Apply at most one threshold update per metric every seven days.",
            ],
        )

    @staticmethod
    def _touches_sensitive_paths(paths: list[str]) -> bool:
        if not paths:
            return False
        sensitive_tokens = (
            "auth",
            "secret",
            "deploy",
            ".github/workflows",
            "ops/azure",
            "app/services/autoprompt/gitops.py",
            "app/api/gitops.py",
            "app/cli.py",
        )
        lowered = [path.lower() for path in paths]
        return any(any(token in path for token in sensitive_tokens) for path in lowered)

    @staticmethod
    def _bounded_threshold_updates(
        *,
        metrics: list[GitMetaPlanMetric],
        churn: float,
        high_risk: bool,
    ) -> list[GitMetaSquaredThresholdUpdate]:
        if not high_risk and churn < 0.2:
            return []

        updates: list[GitMetaSquaredThresholdUpdate] = []
        adjust = min(0.05, 0.02 + (churn * 0.05))
        for metric in metrics[:3]:
            if metric.direction == "HIGHER_IS_BETTER":
                proposed_warn = max(0.0, metric.warn_threshold - adjust)
                proposed_critical = max(0.0, metric.critical_threshold - adjust)
            else:
                proposed_warn = min(1_000_000.0, metric.warn_threshold + adjust)
                proposed_critical = min(1_000_000.0, metric.critical_threshold + adjust)
            updates.append(
                GitMetaSquaredThresholdUpdate(
                    metric_id=metric.metric_id,
                    previous_warn_threshold=metric.warn_threshold,
                    previous_critical_threshold=metric.critical_threshold,
                    proposed_warn_threshold=round(proposed_warn, 6),
                    proposed_critical_threshold=round(proposed_critical, 6),
                    bounded=True,
                    rationale="Patch-level meta-squared trigger requested threshold hardening/relaxation.",
                )
            )
        return updates

    def _handoff_response(
        self,
        *,
        objective: str,
        dry_run: bool,
        branch_name: str,
        pathspec: list[str] | None = None,
        before: GitRepoSnapshot,
        after: GitRepoSnapshot,
        meta_plan: GitMetaPlanResponse,
        steps: list[GitExecutionStep],
        session_id: str,
        trace_id: str,
    ) -> GitHandoffResponse:
        succeeded = sum(1 for row in steps if row.status == "SUCCEEDED")
        failed = sum(1 for row in steps if row.status == "FAILED")
        planned = sum(1 for row in steps if row.status == "PLANNED")
        skipped = sum(1 for row in steps if row.status == "SKIPPED")

        if dry_run:
            status = "DRY_RUN"
        else:
            status = "FAILED" if failed > 0 else "SUCCEEDED"

        return GitHandoffResponse(
            handoff_id=f"handoff_{uuid4().hex[:12]}",
            objective=objective,
            status=status,
            dry_run=dry_run,
            branch_name=branch_name,
            pathspec=pathspec or [],
            repo_snapshot_before=before,
            repo_snapshot_after=after,
            meta_plan=meta_plan,
            steps=steps,
            summary={
                "steps_total": len(steps),
                "steps_succeeded": succeeded,
                "steps_failed": failed,
                "steps_planned": planned,
                "steps_skipped": skipped,
            },
            session_id=session_id,
            trace_id=trace_id,
        )

    def _run_step(
        self,
        *,
        step_id: str,
        description: str,
        command: list[str],
        dry_run: bool,
        requires_tool: str | None = None,
    ) -> GitExecutionStep:
        command_text = " ".join(command)
        if dry_run:
            return GitExecutionStep(
                step_id=step_id,
                description=description,
                command=command_text,
                status="PLANNED",
                requires_tool=requires_tool,
            )

        if requires_tool and shutil.which(requires_tool) is None:
            return GitExecutionStep(
                step_id=step_id,
                description=description,
                command=command_text,
                status="FAILED",
                return_code=127,
                stderr_excerpt=f"Required tool '{requires_tool}' is not installed.",
                requires_tool=requires_tool,
            )

        proc = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return GitExecutionStep(
            step_id=step_id,
            description=description,
            command=command_text,
            status="SUCCEEDED" if proc.returncode == 0 else "FAILED",
            return_code=proc.returncode,
            stdout_excerpt=self._clip(proc.stdout),
            stderr_excerpt=self._clip(proc.stderr),
            requires_tool=requires_tool,
        )

    @staticmethod
    def _clip(value: str, limit: int = 500) -> str | None:
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) <= limit:
            return trimmed
        return trimmed[:limit] + "...<truncated>"

    @staticmethod
    def _parse_test_command(command: str) -> list[str]:
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = []
        if parts:
            return parts
        return ["python", "-m", "pytest", "tests/test_gitops_api.py", "tests/test_gitops_mocking.py", "-q"]

    @staticmethod
    def _normalize_pathspec(pathspec: list[str]) -> tuple[list[str], list[str]]:
        cleaned: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()
        for raw in pathspec:
            value = (raw or "").strip()
            if not value:
                continue
            normalized = value.replace("\\", "/")
            if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
                invalid.append(value)
                continue
            if normalized == ".." or normalized.startswith("..\\") or "\\..\\" in value:
                invalid.append(value)
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned, invalid

    def _scoped_changes_for_pathspec(self, pathspec: list[str]) -> _PathspecScopeStatus:
        command = ["status", "--porcelain", "--untracked-files=all", "--", *pathspec]
        code, out, err = self._run_git(command)
        if code != 0:
            return _PathspecScopeStatus(
                return_code=code,
                command="git " + " ".join(command),
                stdout=out,
                stderr=err,
                changed_paths=[],
            )
        _, _, _, _, _, changed_paths = self._parse_porcelain_status(out)
        return _PathspecScopeStatus(
            return_code=code,
            command="git " + " ".join(command),
            stdout=out,
            stderr=err,
            changed_paths=changed_paths,
        )

    def _bootstrap_command(self, config: GitBootstrapConfig) -> list[str]:
        script_path = self.repo_root / "ops" / "azure" / "bootstrap-and-wire-github.ps1"
        command = [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Repo",
            config.repo or "",
            "-ResourceGroup",
            config.resource_group or "",
            "-Location",
            config.location,
            "-ContainerAppEnvironment",
            config.container_app_environment,
            "-ContainerAppName",
            config.container_app_name,
            "-StaticWebAppName",
            config.static_web_app_name,
            "-DatabaseUrl",
            config.database_url,
        ]
        if config.acr_name:
            command.extend(["-AcrName", config.acr_name])
        return command

    @staticmethod
    def _missing_bootstrap_fields(config: GitBootstrapConfig) -> list[str]:
        missing: list[str] = []
        if not config.repo:
            missing.append("bootstrap.repo")
        if not config.resource_group:
            missing.append("bootstrap.resource_group")
        return missing

    def _branch_hygiene(self) -> tuple[list[str], list[str]]:
        now = int(time.time())
        stale: list[str] = []
        merged: list[str] = []

        code, out, _ = self._run_git(
            ["for-each-ref", "--format=%(refname:short)|%(committerdate:unix)", "refs/heads"]
        )
        if code == 0:
            for line in out.splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                name, ts = line.split("|", 1)
                if name in self._DEFAULT_PROTECTED_BRANCHES:
                    continue
                try:
                    age_days = max(0, (now - int(ts)) // 86400)
                except ValueError:
                    continue
                if age_days >= self._STALE_DAYS:
                    stale.append(name)

        code, out, _ = self._run_git(["branch", "--merged"])
        if code == 0:
            for raw in out.splitlines():
                branch = raw.strip().lstrip("*").strip()
                if not branch or branch in self._DEFAULT_PROTECTED_BRANCHES:
                    continue
                if branch not in merged:
                    merged.append(branch)

        return sorted(stale), sorted(merged)

    def _primary_remote(self) -> tuple[str | None, str | None]:
        code, out, _ = self._run_git(["remote", "-v"])
        if code != 0:
            return None, None
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            name, url, kind = parts[0], parts[1], parts[2]
            if kind == "(fetch)":
                return name, url
        return None, None

    def _parse_porcelain_status(self, text: str) -> tuple[int, int, int, int, int, list[str]]:
        staged = 0
        modified = 0
        untracked = 0
        ahead = 0
        behind = 0
        changed_paths: list[str] = []

        lines = text.splitlines()
        if lines and lines[0].startswith("##"):
            header = lines[0]
            bracket = self._BRANCH_TRACK_RE.search(header)
            if bracket:
                tracking = bracket.group("tracking")
                ahead_match = self._AHEAD_RE.search(tracking)
                behind_match = self._BEHIND_RE.search(tracking)
                if ahead_match:
                    ahead = int(ahead_match.group("count"))
                if behind_match:
                    behind = int(behind_match.group("count"))
            lines = lines[1:]

        for line in lines:
            if not line:
                continue
            if line.startswith("??"):
                untracked += 1
                path = line[3:].strip()
                if path:
                    changed_paths.append(path)
                continue
            if len(line) < 2:
                continue
            x, y = line[0], line[1]
            if x not in {" ", "?"}:
                staged += 1
            if y != " ":
                modified += 1
            if len(line) > 3:
                raw_path = line[3:].strip()
                if " -> " in raw_path:
                    raw_path = raw_path.split(" -> ", 1)[1].strip()
                if raw_path:
                    changed_paths.append(raw_path)

        deduped_paths = sorted(set(changed_paths))
        return staged, modified, untracked, ahead, behind, deduped_paths

    @staticmethod
    def _slugify(text: str) -> str:
        lowered = text.lower().strip()
        lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
        lowered = lowered.strip("-")
        return lowered or "work"

    def _run_git(self, args: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _git_or(self, *args: str, default: str) -> str:
        code, out, _ = self._run_git(list(args))
        if code != 0:
            return default
        value = out.strip()
        return value or default
