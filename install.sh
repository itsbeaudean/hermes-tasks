#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TASK_FILE="${HERMES_TASKS_PATH:-$HOME/tasks.md}"

if ! command -v hermes >/dev/null 2>&1; then
  printf 'Hermes CLI was not found. Install Hermes first: https://hermes-agent.nousresearch.com/docs\n' >&2
  exit 1
fi

install -d "$HERMES_HOME/desktop-plugins/tasks"
install -d "$HERMES_HOME/plugins/tasks/dashboard"

install -m 0644 "$REPO_ROOT/desktop-plugins/tasks/plugin.js" "$HERMES_HOME/desktop-plugins/tasks/plugin.js"
install -m 0644 "$REPO_ROOT/plugins/tasks/plugin.yaml" "$HERMES_HOME/plugins/tasks/plugin.yaml"
install -m 0644 "$REPO_ROOT/plugins/tasks/dashboard/manifest.json" "$HERMES_HOME/plugins/tasks/dashboard/manifest.json"
install -m 0644 "$REPO_ROOT/plugins/tasks/dashboard/plugin_api.py" "$HERMES_HOME/plugins/tasks/dashboard/plugin_api.py"

if [[ ! -e "$TASK_FILE" ]]; then
  install -d "$(dirname "$TASK_FILE")"
  cat >"$TASK_FILE" <<'EOF'
# Tasks

Updated: 2026-08-02

## Now

## Waiting

## Later

## Done
EOF
  printf 'Created %s\n' "$TASK_FILE"
fi

HERMES_HOME="$HERMES_HOME" hermes plugins enable tasks --no-allow-tool-override

printf '\nInstalled Tasks for Hermes Desktop.\n'
printf '1. Fully quit and reopen Hermes Desktop so the task backend is mounted.\n'
printf '2. Open Hermes Desktop and run "Reload desktop plugins" from the command palette if Tasks does not appear.\n'
printf '3. Your task file is %s\n' "$TASK_FILE"
printf '\nTo use a different file, set HERMES_TASKS_PATH in the environment that starts your Hermes gateway, then restart it.\n'
