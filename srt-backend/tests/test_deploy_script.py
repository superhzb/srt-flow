from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh"


def _run(*args: str, cwd: Path) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def deployment_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    clone = tmp_path / "clone"
    remote.mkdir()
    source.mkdir()
    _run("git", "init", "--bare", cwd=remote)
    _run("git", "init", "-b", "staging", cwd=source)
    _run("git", "config", "user.name", "CI", cwd=source)
    _run("git", "config", "user.email", "ci@example.com", cwd=source)
    (source / "version.txt").write_text("one\n")
    for directory in (
        "srt-backend",
        "srt-frontend",
    ):
        package_dir = source / directory
        package_dir.mkdir()
        (package_dir / ".keep").write_text("")
    _run("git", "add", ".", cwd=source)
    _run("git", "commit", "-m", "initial", cwd=source)
    first_sha = _run("git", "rev-parse", "HEAD", cwd=source)
    _run("git", "remote", "add", "origin", str(remote), cwd=source)
    _run("git", "push", "-u", "origin", "staging", cwd=source)
    _run("git", "clone", "--branch", "staging", str(remote), str(clone), cwd=tmp_path)
    return source, clone, first_sha


def _deploy_env(tmp_path: Path, clone: Path, expected_sha: str) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    actions = tmp_path / "router-actions"
    database_revision = tmp_path / "database-revision"
    database_revision.write_text("0007_job_carried_langs\n")
    _write_executable(
        fake_bin / "shlock",
        """#!/bin/bash
while [[ $# -gt 0 ]]; do
  [[ $1 == -f ]] && { shift; touch "$1"; }
  shift || true
done
""",
    )
    _write_executable(
        fake_bin / "uv",
        """#!/bin/bash
if [[ $1 == run && $2 == python ]]; then
  cat "$DB_REVISION_FILE"
fi
""",
    )
    _write_executable(
        fake_bin / "npm",
        '#!/bin/bash\nprintf \'%s\\n\' "$*" >> "$NPM_ACTIONS"\n',
    )
    _write_executable(
        fake_bin / "curl",
        """#!/bin/bash
url=${!#}
case "$url" in
  */api/projects)
    project_json='{"projects":[{"name":"srt-flow-stg","resourceGroup":"mlx","status":"%s"}]}'
    printf "$project_json" "${PROJECT_STATUS:-stopped}"
    ;;
  */api/projects/*)
    printf '%s\n' "$url" >> "$ROUTER_ACTIONS"
    if [[ $url == */start && -n ${MIGRATE_ON_START:-} ]]; then
      printf '%s\n' "$MIGRATE_ON_START" > "$DB_REVISION_FILE"
    fi
    printf '%s' '{"ok":true}'
    ;;
  */api/health)
    if [[ ${FAIL_HEALTH:-0} == 1 ]]; then
      printf '%s' '{"error":"missing auth configuration"}'
      exit 22
    fi
    if [[ ${FAIL_HEALTH_ONCE:-0} == 1 && ! -e $HEALTH_FAILURE_MARKER ]]; then
      touch "$HEALTH_FAILURE_MARKER"
      printf '%s' '{"error":"missing auth configuration"}'
      exit 22
    fi
    commit=$(git -C "$DEPLOY_CLONE" rev-parse HEAD)
    printf '{"status":"ok","commit":"%s"}' "$commit"
    ;;
  */api/workers)
    printf '%s' '{"workers":[{"id":"mlx","healthy":true}]}'
    ;;
  *) exit 22 ;;
esac
""",
    )
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SRT_FLOW_STAGING_CLONE": str(clone),
        "SRT_FLOW_DEPLOY_STATE_DIR": str(tmp_path / "state"),
        "BRBOT_ROUTER_DASHBOARD_HOST": "dashboard.example.com",
        "BRBOT_ROUTER_PASSCODE": "test-passcode",
        "ROUTER_ACTIONS": str(actions),
        "EXPECTED_SHA": expected_sha,
        "DEPLOY_CLONE": str(clone),
        "DB_REVISION_FILE": str(database_revision),
        "HEALTH_FAILURE_MARKER": str(tmp_path / "health-failed"),
        "NPM_ACTIONS": str(tmp_path / "npm-actions"),
    }


def test_deploys_only_the_ci_event_sha(
    tmp_path: Path, deployment_repo: tuple[Path, Path, str]
) -> None:
    source, clone, first_sha = deployment_repo
    (source / "version.txt").write_text("two\n")
    _run("git", "add", "version.txt", cwd=source)
    _run("git", "commit", "-m", "second", cwd=source)
    second_sha = _run("git", "rev-parse", "HEAD", cwd=source)
    _run("git", "push", "origin", "staging", cwd=source)
    env = _deploy_env(tmp_path, clone, second_sha)

    result = subprocess.run(
        [str(SCRIPT), "staging", second_sha],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert _run("git", "rev-parse", "HEAD", cwd=clone) == second_sha
    assert "started and health-checked" in result.stdout
    assert (
        (tmp_path / "router-actions")
        .read_text()
        .strip()
        .endswith("/api/projects/srt-flow-stg/start")
    )
    assert first_sha != second_sha
    assert (tmp_path / "npm-actions").read_text().splitlines() == ["ci", "run build"]


def test_skips_when_branch_advanced_past_tested_sha(
    tmp_path: Path, deployment_repo: tuple[Path, Path, str]
) -> None:
    source, clone, tested_sha = deployment_repo
    (source / "version.txt").write_text("untested\n")
    _run("git", "add", "version.txt", cwd=source)
    _run("git", "commit", "-m", "untested", cwd=source)
    _run("git", "push", "origin", "staging", cwd=source)
    env = _deploy_env(tmp_path, clone, tested_sha)

    result = subprocess.run(
        [str(SCRIPT), "staging", tested_sha],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert _run("git", "rev-parse", "HEAD", cwd=clone) == tested_sha
    assert "skipping stale deployment" in result.stdout
    assert not (tmp_path / "router-actions").exists()


def test_restores_previous_commit_and_active_project_on_failure(
    tmp_path: Path, deployment_repo: tuple[Path, Path, str]
) -> None:
    source, clone, previous_sha = deployment_repo
    (source / "version.txt").write_text("broken\n")
    _run("git", "add", "version.txt", cwd=source)
    _run("git", "commit", "-m", "broken", cwd=source)
    broken_sha = _run("git", "rev-parse", "HEAD", cwd=source)
    _run("git", "push", "origin", "staging", cwd=source)
    env = {
        **_deploy_env(tmp_path, clone, broken_sha),
        "PROJECT_STATUS": "running",
        "FAIL_HEALTH": "1",
    }

    result = subprocess.run(
        [str(SCRIPT), "staging", broken_sha],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert _run("git", "rev-parse", "HEAD", cwd=clone) == previous_sha
    actions = (tmp_path / "router-actions").read_text().splitlines()
    assert actions[-2:] == [
        "http://127.0.0.1:9000/api/projects/srt-flow-stg/stop",
        "http://127.0.0.1:9000/api/projects/srt-flow-stg/start",
    ]
    deployment_log = (tmp_path / "state" / "deployments.jsonl").read_text()
    assert '"result":"failed"' in deployment_log


def test_rolls_forward_when_migration_succeeds_before_startup_failure(
    tmp_path: Path, deployment_repo: tuple[Path, Path, str]
) -> None:
    source, clone, previous_sha = deployment_repo
    (source / "version.txt").write_text("migration-aware\n")
    _run("git", "add", "version.txt", cwd=source)
    _run("git", "commit", "-m", "add migration-aware release", cwd=source)
    release_sha = _run("git", "rev-parse", "HEAD", cwd=source)
    _run("git", "push", "origin", "staging", cwd=source)
    env = {
        **_deploy_env(tmp_path, clone, release_sha),
        "PROJECT_STATUS": "running",
        "MIGRATE_ON_START": "0008_ledger_receipt_url",
        "FAIL_HEALTH_ONCE": "1",
    }

    result = subprocess.run(
        [str(SCRIPT), "staging", release_sha],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert _run("git", "rev-parse", "HEAD", cwd=clone) == release_sha
    assert previous_sha != release_sha
    assert "missing auth configuration" in result.stderr
    assert "Roll-forward recovery succeeded" in result.stderr
    actions = (tmp_path / "router-actions").read_text().splitlines()
    assert actions[-2:] == [
        "http://127.0.0.1:9000/api/projects/srt-flow-stg/stop",
        "http://127.0.0.1:9000/api/projects/srt-flow-stg/start",
    ]
    deployment_log = (tmp_path / "state" / "deployments.jsonl").read_text()
    assert f'"previousCommit":"{previous_sha}"' in deployment_log
    assert '"preDeployRevision":"0007_job_carried_langs"' in deployment_log
    assert '"databaseRevision":"0008_ledger_receipt_url"' in deployment_log
    assert "retained and restarted code" in deployment_log
