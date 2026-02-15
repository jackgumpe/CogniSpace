from __future__ import annotations

import subprocess

from app.models.gitops import GitHandoffRequest, GitMetaPlanRequest
from app.services.autoprompt.gitops import GitOpsAdvisor
from tests.helpers.git_repo_factory import GitRepoFactory


def _git(repo, *cmd: str) -> str:  # noqa: ANN001
    proc = subprocess.run(
        list(cmd),
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc.stdout.strip()


def test_parse_porcelain_status_extracts_changed_paths() -> None:
    advisor = GitOpsAdvisor()
    porcelain = (
        "## main...origin/main [ahead 2, behind 1]\n"
        " M app/cli.py\n"
        "A  app/api/gitops.py\n"
        "R  docs/old.md -> docs/new.md\n"
        "?? .github/workflows/deploy.yml\n"
    )

    staged, modified, untracked, ahead, behind, changed_paths = advisor._parse_porcelain_status(porcelain)
    assert staged == 2
    assert modified == 1
    assert untracked == 1
    assert ahead == 2
    assert behind == 1
    assert ".github/workflows/deploy.yml" in changed_paths
    assert "docs/new.md" in changed_paths


def test_snapshot_in_ephemeral_repo_reports_changed_paths(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo = GitRepoFactory(repo_root).init()
    factory = GitRepoFactory(repo)
    factory.commit_file("README.md", "hello\n", "chore: init")
    factory.write_file("README.md", "hello world\n")
    factory.write_file("notes/todo.txt", "draft\n")

    advisor = GitOpsAdvisor(repo_root=repo)
    snapshot = advisor.snapshot()
    assert snapshot.status == "OK"
    assert snapshot.total_changed_files >= 2
    assert "README.md" in snapshot.changed_paths
    assert "notes/todo.txt" in snapshot.changed_paths


def test_meta_plan_patch_mode_triggers_on_high_risk(tmp_path) -> None:  # noqa: ANN001
    repo = GitRepoFactory(tmp_path / "repo").init()
    advisor = GitOpsAdvisor(repo_root=repo)
    response = advisor.meta_plan(
        GitMetaPlanRequest(
            objective="high risk git automation refactor",
            risk_level="HIGH",
            meta_squared_mode="PATCH",
        )
    )
    assert response.meta_squared.enabled is True
    assert response.meta_squared.triggered is True
    assert "risk_level_high" in response.meta_squared.trigger_reasons


def test_meta_plan_patch_mode_triggers_on_sensitive_paths(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo = GitRepoFactory(repo_root).init()
    factory = GitRepoFactory(repo)
    factory.commit_file("README.md", "hello\n", "chore: init")
    factory.write_file(".github/workflows/deploy.yml", "name: deploy\n")

    advisor = GitOpsAdvisor(repo_root=repo)
    response = advisor.meta_plan(
        GitMetaPlanRequest(
            objective="check sensitive change trigger",
            risk_level="LOW",
            meta_squared_mode="PATCH",
        )
    )
    assert response.meta_squared.enabled is True
    assert response.meta_squared.triggered is True
    assert "touches_sensitive_paths" in response.meta_squared.trigger_reasons


def test_meta_plan_off_disables_meta_squared(tmp_path) -> None:  # noqa: ANN001
    repo = GitRepoFactory(tmp_path / "repo").init()
    advisor = GitOpsAdvisor(repo_root=repo)
    response = advisor.meta_plan(
        GitMetaPlanRequest(
            objective="off mode",
            risk_level="HIGH",
            meta_squared_mode="OFF",
        )
    )
    assert response.meta_squared.mode == "OFF"
    assert response.meta_squared.enabled is False
    assert response.meta_squared.triggered is False


def test_handoff_execute_requires_pathspec_on_protected_dirty_branch(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo = GitRepoFactory(repo_root).init()
    factory = GitRepoFactory(repo)
    factory.commit_file("README.md", "hello\n", "chore: init")
    factory.write_file("notes/todo.txt", "draft\n")

    advisor = GitOpsAdvisor(repo_root=repo)
    response = advisor.handoff(
        GitHandoffRequest(
            objective="unsafe execute",
            dry_run=False,
            run_tests=False,
            push_branch=False,
            create_pr=False,
            include_bootstrap=False,
            trigger_workflows=False,
        )
    )

    assert response.status == "FAILED"
    assert any(step.step_id == "safety_guard" and step.status == "FAILED" for step in response.steps)
    assert _git(repo, "git", "rev-parse", "--abbrev-ref", "HEAD") in {"main", "master"}


def test_handoff_execute_with_pathspec_commits_only_scoped_files(tmp_path) -> None:  # noqa: ANN001
    repo_root = tmp_path / "repo"
    repo = GitRepoFactory(repo_root).init()
    factory = GitRepoFactory(repo)
    factory.commit_file("README.md", "hello\n", "chore: init")
    factory.commit_file("app/alpha.txt", "v1\n", "feat: add alpha")
    factory.commit_file("app/beta.txt", "v1\n", "feat: add beta")
    factory.write_file("app/alpha.txt", "v2\n")
    factory.write_file("app/beta.txt", "v2\n")

    advisor = GitOpsAdvisor(repo_root=repo)
    response = advisor.handoff(
        GitHandoffRequest(
            objective="scoped execute",
            dry_run=False,
            run_tests=False,
            pathspec=["app/alpha.txt"],
            push_branch=False,
            create_pr=False,
            include_bootstrap=False,
            trigger_workflows=False,
        )
    )

    assert response.status == "SUCCEEDED"
    assert response.pathspec == ["app/alpha.txt"]
    assert any(step.step_id == "create_feature_branch" and step.status == "SUCCEEDED" for step in response.steps)
    committed_files = [row.strip() for row in _git(repo, "git", "show", "--name-only", "--pretty=format:", "HEAD").splitlines() if row.strip()]
    assert "app/alpha.txt" in committed_files
    assert "app/beta.txt" not in committed_files
    beta_status = _git(repo, "git", "status", "--porcelain", "--", "app/beta.txt")
    assert beta_status
