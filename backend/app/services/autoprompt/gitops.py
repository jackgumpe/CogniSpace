from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from app.models.gitops import (
    GitAdviceRequest,
    GitAdviceResponse,
    GitAgentRecommendation,
    GitRepoSnapshot,
)


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
        status_porcelain = self._git_or("status", "--porcelain", "--branch", default="")
        staged, modified, untracked, ahead, behind = self._parse_porcelain_status(status_porcelain)

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

    def _parse_porcelain_status(self, text: str) -> tuple[int, int, int, int, int]:
        staged = 0
        modified = 0
        untracked = 0
        ahead = 0
        behind = 0

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
                continue
            if len(line) < 2:
                continue
            x, y = line[0], line[1]
            if x not in {" ", "?"}:
                staged += 1
            if y != " ":
                modified += 1

        return staged, modified, untracked, ahead, behind

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
