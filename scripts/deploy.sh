#!/bin/bash

set -Eeuo pipefail

usage() {
  echo "usage: $0 <staging|production> <40-character-commit-sha>" >&2
  exit 64
}

environment=${1:-}
expected_sha=${2:-}
[[ "$environment" == "staging" || "$environment" == "production" ]] || usage
[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]] || usage

deploy_config=${SRT_FLOW_DEPLOY_CONFIG:-"$HOME/.config/srt-flow/deploy.env"}
router_env=${BRBOT_ROUTER_ENV:-"$HOME/Documents/GitHub/brbot-router/.env"}
if [[ -r "$deploy_config" ]]; then
  # shellcheck disable=SC1090
  source "$deploy_config"
elif [[ -r "$router_env" ]]; then
  # Reuse the router's machine-local credentials without copying them into GitHub.
  # shellcheck disable=SC1090
  source "$router_env"
fi

srt_flow_root=${SRT_FLOW_ROOT:-"$HOME/Documents/GitHub/srt-flow"}
router_url=${BRBOT_ROUTER_URL:-"http://127.0.0.1:9000"}
router_host=${BRBOT_ROUTER_DASHBOARD_HOST:-${DASHBOARD_DOMAIN:-}}
router_passcode=${BRBOT_ROUTER_PASSCODE:-${DASHBOARD_PASSCODE:-}}
resource_group=${BRBOT_ROUTER_RESOURCE_GROUP:-mlx}
state_dir=${SRT_FLOW_DEPLOY_STATE_DIR:-"$HOME/Library/Application Support/srt-flow-deploy"}

if [[ "$environment" == "staging" ]]; then
  clone=${SRT_FLOW_STAGING_CLONE:-"$srt_flow_root/srt-flow-staging/srt-flow"}
  branch=staging
  project=srt-flow-stg
  public_url=${SRT_FLOW_STAGING_URL:-"https://staging.srt-flow.com"}
else
  clone=${SRT_FLOW_PRODUCTION_CLONE:-"$srt_flow_root/srt-flow-prod/srt-flow"}
  branch=main
  project=srt-flow
  public_url=${SRT_FLOW_PRODUCTION_URL:-"https://app.srt-flow.com"}
fi

[[ -n "$router_host" ]] || { echo "router dashboard host is not configured" >&2; exit 78; }
[[ -n "$router_passcode" ]] || { echo "router passcode is not configured" >&2; exit 78; }
[[ -d "$clone/.git" ]] || { echo "deployment clone does not exist: $clone" >&2; exit 72; }

mkdir -p "$state_dir"
lock_file="$state_dir/deploy.lock"
if ! shlock -f "$lock_file" -p $$; then
  echo "another srt-flow deployment holds $lock_file" >&2
  exit 75
fi

cleanup_lock() {
  rm -f "$lock_file"
}
trap cleanup_lock EXIT

log_result() {
  local result=$1
  local detail=$2
  jq -cn \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg environment "$environment" \
    --arg commit "$expected_sha" \
    --arg previous_commit "$previous_sha" \
    --arg pre_deploy_revision "$pre_deploy_revision" \
    --arg database_revision "$current_database_revision" \
    --arg result "$result" \
    --arg detail "$detail" \
    '{timestamp:$timestamp,environment:$environment,commit:$commit,
      previousCommit:$previous_commit,preDeployRevision:$pre_deploy_revision,
      databaseRevision:$database_revision,result:$result,detail:$detail}' \
    >> "$state_dir/deployments.jsonl"
}

router_get() {
  curl --fail --silent --show-error \
    -H "Host: $router_host" \
    "$router_url/api/projects"
}

router_action() {
  local target_project=$1
  local action=$2
  local response status
  response=$(curl --fail-with-body --silent --show-error \
    -X POST \
    -H "Host: $router_host" \
    -H "Authorization: Bearer $router_passcode" \
    "$router_url/api/projects/$target_project/$action") || {
    status=$?
    echo "router $action failed for $target_project: ${response:-no response body}" >&2
    return "$status"
  }
}

project_is_active() {
  local statuses=$1
  local target_project=$2
  jq -e --arg project "$target_project" \
    '.projects[] | select(.name == $project) | (.status == "running" or .status == "idle")' \
    >/dev/null <<<"$statuses"
}

active_resource_project() {
  local statuses=$1
  jq -r --arg group "$resource_group" \
    '[.projects[] | select(.resourceGroup == $group and (.status == "running" or .status == "idle"))][0].name // ""' \
    <<<"$statuses"
}

install_dependencies() {
  {
    (cd "$clone/srt-backend" && uv sync --frozen --all-extras) &&
      (cd "$clone/srt-frontend" && npm ci && npm run build)
  } || return $?
}

database_revision() {
  (
    cd "$clone/srt-backend"
    uv run python -c '
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

root = Path.cwd()
load_dotenv(root / ".env")
environment = os.getenv("ENV", "dev")
if environment != "dev":
    load_dotenv(root / f".env.{environment}", override=True)
url = os.environ.get("DATABASE_URL", "sqlite:///./.data/dev/db.sqlite")
engine = create_engine(url)
with engine.connect() as connection:
    if "alembic_version" not in inspect(connection).get_table_names():
        print("base")
    else:
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
        print(",".join(sorted(revisions)) or "base")
'
  )
}

verify_health() {
  local commit=${1:-$expected_sha}
  local health workers status
  health=$(curl --fail-with-body --silent --show-error --retry 10 --retry-delay 2 \
    "$public_url/api/health") || {
    status=$?
    echo "health check failed: ${health:-no response body}" >&2
    return "$status"
  }
  jq -e --arg commit "$commit" \
    '.status == "ok" and .commit == $commit' >/dev/null <<<"$health" || {
    echo "health check returned an unexpected response: $health" >&2
    return 1
  }

  workers=$(curl --fail-with-body --silent --show-error --retry 5 --retry-delay 2 \
    "$public_url/api/workers") || {
    status=$?
    echo "worker health check failed: ${workers:-no response body}" >&2
    return "$status"
  }
  jq -e '.workers | length > 0 and all(.healthy == true)' >/dev/null <<<"$workers" || {
    echo "worker health check returned an unexpected response: $workers" >&2
    return 1
  }
}

previous_sha=
pre_deploy_revision=
current_database_revision=
previous_active_project=
mutation_started=false
should_start=false

rollback() {
  local reason=$1
  local recovery_detail="no deployment mutation required recovery"
  local recovery_project revision_reason revision_status
  trap - ERR INT TERM
  set +e

  if [[ "$mutation_started" == true && -n "$previous_sha" ]]; then
    echo "::error title=Deployment failed::$reason" >&2
    current_database_revision=$(database_revision 2>&1)
    revision_status=$?
    router_action "$project" stop

    if [[ $revision_status -eq 0 && "$current_database_revision" == "$pre_deploy_revision" ]]; then
      echo "database remains at $current_database_revision; restoring code $previous_sha" >&2
      git -C "$clone" reset --hard "$previous_sha" >/dev/null
      recovery_project=$previous_active_project
      [[ -n "$recovery_project" || "$should_start" != true ]] || recovery_project=$project
      if install_dependencies && { [[ -z "$recovery_project" ]] ||
        { router_action "$recovery_project" start && verify_health "$previous_sha"; }; }; then
        recovery_detail="restored code $previous_sha and unchanged database revision $current_database_revision"
        echo "::notice title=Deployment recovery succeeded::$recovery_detail" >&2
      else
        recovery_detail="failed to restore a healthy previous release; manual recovery required"
        echo "::error title=Deployment recovery failed::$recovery_detail" >&2
      fi
    else
      # Never downgrade automatically. A failed downgrade is substantially harder to
      # recover from, and the deployment process does not create a database backup.
      if [[ $revision_status -ne 0 ]]; then
        current_database_revision="unknown"
        revision_reason="database revision could not be read"
      else
        revision_reason="database advanced from $pre_deploy_revision to $current_database_revision"
      fi
      echo "$revision_reason; retaining migration-aware code $expected_sha" >&2
      if install_dependencies && router_action "$project" start && verify_health "$expected_sha"; then
        recovery_detail="$revision_reason; retained and restarted code $expected_sha"
        echo "::notice title=Roll-forward recovery succeeded::$recovery_detail" >&2
      else
        recovery_detail="$revision_reason; retained code $expected_sha but startup failed; manual recovery required"
        echo "::error title=Manual recovery required::$recovery_detail" >&2
      fi
    fi
  fi

  log_result failed "$reason; recovery: $recovery_detail"
}

handle_error() {
  local status=$1
  local line=$2
  rollback "command failed with status $status at line $line"
  exit "$status"
}

handle_signal() {
  local signal=$1
  rollback "received $signal"
  exit 130
}

trap 'handle_error $? $LINENO' ERR
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

if [[ -n "$(git -C "$clone" status --porcelain)" ]]; then
  echo "deployment clone is dirty: $clone" >&2
  exit 65
fi

current_branch=$(git -C "$clone" symbolic-ref --quiet --short HEAD || true)
if [[ "$current_branch" != "$branch" ]]; then
  echo "deployment clone must be on $branch (found ${current_branch:-detached})" >&2
  exit 65
fi

git -C "$clone" fetch --no-tags origin \
  "+refs/heads/$branch:refs/remotes/origin/$branch"
remote_sha=$(git -C "$clone" rev-parse "origin/$branch")
if [[ "$remote_sha" != "$expected_sha" ]]; then
  echo "skipping stale deployment: origin/$branch is $remote_sha, workflow tested $expected_sha"
  log_result skipped "remote branch advanced to $remote_sha"
  exit 0
fi

previous_sha=$(git -C "$clone" rev-parse HEAD)
if ! git -C "$clone" merge-base --is-ancestor "$previous_sha" "$expected_sha"; then
  echo "$branch cannot fast-forward from $previous_sha to $expected_sha" >&2
  exit 65
fi

pre_deploy_revision=$(database_revision)
current_database_revision=$pre_deploy_revision
log_result started "pre-deploy state recorded"
echo "deploying $previous_sha ($pre_deploy_revision) -> $expected_sha" >&2

statuses=$(router_get) || { echo "could not read router status" >&2; false; }
previous_active_project=$(active_resource_project "$statuses")
target_was_active=false
if project_is_active "$statuses" "$project"; then
  target_was_active=true
fi

mutation_started=true
if [[ "$target_was_active" == true ]]; then
  router_action "$project" stop
fi

git -C "$clone" merge --ff-only "$expected_sha"
install_dependencies

if [[ "$environment" == "production" || "$target_was_active" == true || -z "$previous_active_project" ]]; then
  should_start=true
fi

if [[ "$should_start" == true ]]; then
  # An authenticated start atomically preempts any project in the MLX resource group.
  router_action "$project" start
  verify_health
  detail="started and health-checked"
else
  detail="updated while $previous_active_project remained active"
fi

mutation_started=false
if ! current_database_revision=$(database_revision); then
  current_database_revision="unknown"
fi
log_result succeeded "$detail"
echo "$environment deployed at $expected_sha ($detail)"
