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
  public_url=${SRT_FLOW_PRODUCTION_URL:-"https://www.srt-flow.com"}
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
    --arg result "$result" \
    --arg detail "$detail" \
    '{timestamp:$timestamp,environment:$environment,commit:$commit,result:$result,detail:$detail}' \
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
  curl --fail --silent --show-error \
    -X POST \
    -H "Host: $router_host" \
    -H "Authorization: Bearer $router_passcode" \
    "$router_url/api/projects/$target_project/$action" >/dev/null
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

verify_health() {
  local health workers
  health=$(curl --fail --silent --show-error --retry 10 --retry-delay 2 \
    "$public_url/api/health") || return $?
  jq -e --arg commit "$expected_sha" \
    '.status == "ok" and .commit == $commit' >/dev/null <<<"$health" || return $?

  workers=$(curl --fail --silent --show-error --retry 5 --retry-delay 2 \
    "$public_url/api/workers") || return $?
  jq -e '.workers | length > 0 and all(.healthy == true)' >/dev/null <<<"$workers" || return $?
}

previous_sha=
previous_active_project=
mutation_started=false

rollback() {
  local reason=$1
  trap - ERR INT TERM
  set +e

  if [[ "$mutation_started" == true && -n "$previous_sha" ]]; then
    echo "deployment failed; restoring $previous_sha" >&2
    router_action "$project" stop
    git -C "$clone" reset --hard "$previous_sha" >/dev/null
    install_dependencies
    if [[ -n "$previous_active_project" ]]; then
      router_action "$previous_active_project" start
    fi
  fi

  log_result failed "$reason"
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

should_start=false
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
log_result succeeded "$detail"
echo "$environment deployed at $expected_sha ($detail)"
