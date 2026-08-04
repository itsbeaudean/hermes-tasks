#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TASK_FILE="${HERMES_TASKS_PATH:-$HOME/tasks.md}"

if ! command -v hermes >/dev/null 2>&1; then
  printf 'Hermes CLI was not found. Install Hermes first: https://hermes-agent.nousresearch.com/docs\n' >&2
  exit 1
fi

if [[ ! -e "$TASK_FILE" ]]; then
  install -d "$(dirname "$TASK_FILE")"
  cat >"$TASK_FILE" <<EOF
# Tasks

Areas: work, life
Doing limit: 3

Updated: $(date +%F)

## Next

## Doing

## Waiting

## Later

## Done
EOF
  printf 'Created %s\n' "$TASK_FILE"
else
  HERMES_TASKS_PATH="$TASK_FILE" TASKS_PLUGIN_API="$REPO_ROOT/plugins/tasks/dashboard/plugin_api.py" python3 <<'PY'
import importlib.util
import os
from pathlib import Path
import re
import shutil
from datetime import datetime

module_path = Path(os.environ["TASKS_PLUGIN_API"])
task_path = Path(os.environ["HERMES_TASKS_PATH"])
spec = importlib.util.spec_from_file_location("hermes_tasks_install", module_path)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load the Tasks migration module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

markdown = task_path.read_text(encoding="utf-8")
parsed = module.parse_board(markdown)
needs_migration = (
    re.search(r"(?m)^## Now[ \t]*\r?$", markdown) is not None
    or not module.AREAS_LINE_RE.search(markdown)
    or not module.DOING_LIMIT_RE.search(markdown)
    or not any(line.strip() == "## Doing" for line in markdown.splitlines())
    or any(
        not module.TASK_ID_RE.search(task["raw_title"])
        for tasks in parsed["sections"].values()
        for task in tasks
    )
)
if needs_migration:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = task_path.with_name(f"{task_path.name}.pre-v2-{stamp}.bak")
    shutil.copy2(task_path, backup)
    module.TaskStore(task_path).migrate()
    print(f"Migrated {task_path} to Tasks V2 (backup: {backup})")
PY
fi

install -d "$HERMES_HOME/desktop-plugins/tasks"
install -d "$HERMES_HOME/plugins/tasks/dashboard"

install -m 0644 "$REPO_ROOT/desktop-plugins/tasks/plugin.js" "$HERMES_HOME/desktop-plugins/tasks/plugin.js"
install -m 0644 "$REPO_ROOT/plugins/tasks/plugin.yaml" "$HERMES_HOME/plugins/tasks/plugin.yaml"
install -m 0644 "$REPO_ROOT/plugins/tasks/dashboard/manifest.json" "$HERMES_HOME/plugins/tasks/dashboard/manifest.json"
install -m 0644 "$REPO_ROOT/plugins/tasks/dashboard/plugin_api.py" "$HERMES_HOME/plugins/tasks/dashboard/plugin_api.py"

HERMES_HOME="$HERMES_HOME" hermes plugins enable tasks --no-allow-tool-override

printf '\nInstalled Tasks for Hermes Desktop.\n'
printf '1. Fully quit and reopen Hermes Desktop so the task backend is mounted.\n'
printf '2. Open Hermes Desktop and run "Reload desktop plugins" from the command palette if Tasks does not appear.\n'
printf '3. Your task file is %s\n' "$TASK_FILE"
printf '\nTo use a different file, set HERMES_TASKS_PATH in the environment that starts your Hermes backend, then restart it.\n'
