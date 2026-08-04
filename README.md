# Hermes Tasks

A small, local personal Kanban board shared by you and Hermes.

It adds a **Tasks** page in the sidebar and a compact task count in the status bar. Tasks live in a normal Markdown file, so there is no account, hosted database, or separate task app to maintain.

## Intentionally simple

This is deliberately a small local plugin:

- one `tasks.md` file is the source of truth
- one JavaScript file adds the Hermes Desktop page and status item
- one small Python backend reads and updates that Markdown file

There is no account, sync service, database, or proprietary format to remain compatible with. If you stop using the plugin, your tasks are still just a readable Markdown file.

![Hermes Desktop plugin](https://img.shields.io/badge/Hermes-Desktop%20plugin-6d5efc)

## What it does

- Uses the workflow `Next → Doing → Waiting → Done`, with a quiet `Later` lane
- Lets every person create, rename, and remove their own areas
- Keeps areas independent from workflow status: areas are filters, not columns
- Folds each workflow lane independently; folded lanes remain valid drop targets
- Supports native drag-and-drop ordering, editing, completion, reopening, and priority
- Keeps stable task IDs while tasks move or their metadata changes
- Makes agent involvement explicit through **Ask Hermes**
- Keeps the source of truth in one local `tasks.md` file

`Work` and `Life` are ordinary starter areas, not permanent system categories. Remove them, rename them, or replace them with whatever matches your life.

## Features

| Feature | What you can do |
|---|---|
| Personal Kanban workflow | Move work through **Next**, **Doing**, **Waiting**, **Later**, and **Done**. |
| Native drag and drop | Move cards between lanes and reorder cards within a lane without installing a drag-and-drop library. |
| Foldable lanes | Fold every lane independently into a narrow rail. Folded lanes still show their count and accept dropped cards. |
| User-defined areas | Create any areas that suit you—projects, responsibilities, clients, study, health, family, or none at all. |
| Area management | Rename areas, remove them, reassign affected tasks, or leave those tasks unassigned. Removing an area never removes a task. |
| Area and priority filters | Narrow the board by an area or priority without changing the underlying tasks. |
| Search | Search task titles and areas across the board. |
| Task editing | Change a task's title, workflow status, area, and priority from its card. |
| Completion and reopening | Completing a task moves it to **Done** and records the date. Reopening removes completion metadata and makes it actionable again. |
| Soft WIP guidance | See when **Doing** exceeds its configurable limit without being blocked from making the choice. |
| Stable identity and ordering | Task IDs survive edits, moves, area changes, and reordering. Revision checks prevent stale writes from silently winning. |
| Explicit **Ask Hermes** | Send one task's context to Hermes only when you choose. Opening or selecting a task never silently starts an agent. |
| Plain-Markdown source | Read or edit `tasks.md` with any text editor. There is no hosted account, database, or proprietary task store. |
| Desktop integration | Open Tasks from the Hermes sidebar or its compact status-bar count. Keyboard shortcuts focus search (`/`) and new-task entry (`N`). |
| Safe concurrent changes | Atomic writes, stable revisions, and process-safe locking protect the file when Desktop and Hermes both operate on it. |

## Install

**Requirements:** Hermes Desktop and the Hermes CLI must already be installed.

### Ask Hermes to install it

If you use Hermes already, copy the prompt in [PROMPT.md](PROMPT.md) into a Hermes chat. It asks your agent to inspect the plugin, install it without overwriting an existing task file, verify the required files, and tell you exactly when to restart Desktop.

### Install manually

```bash
git clone https://github.com/itsbeaudean/hermes-tasks.git
cd hermes-tasks
chmod +x install.sh
./install.sh
```

The installer copies the two required pieces into your active Hermes home:

```text
$HERMES_HOME/desktop-plugins/tasks/plugin.js
$HERMES_HOME/plugins/tasks/dashboard/{manifest.json,plugin_api.py}
```

It then enables the Python backend with `hermes plugins enable tasks --no-allow-tool-override` and creates `~/tasks.md` if you do not already have one. The plugin has no need to replace Hermes' built-in tools, so the installer explicitly declines that privileged capability.

Fully quit and reopen Hermes Desktop after installation so its backend mounts the task API. If **Tasks** does not appear in the sidebar within a few seconds, open the command palette and run **Reload desktop plugins**.

## How to use it

Open **Tasks** from the Hermes Desktop sidebar. The small count in the status bar also opens the page.

1. Type a concrete next action, choose its status and optional area, then select **Add**.
2. Drag cards between `Next`, `Doing`, `Waiting`, and `Later`, or drag within a lane to reorder them.
3. Tick a task to move it to **Done**. Reopen it to return it to an actionable state and remove its completion metadata.
4. Use area and priority filters to narrow the board without changing task status.
5. Fold any lane with its arrow. Click the narrow vertical rail to reopen it. `Later` starts folded by default.
6. Open a card to edit it. **Ask Hermes** is a separate explicit action; selecting a task never silently starts an agent.
7. Edit the Markdown file directly whenever you prefer, then refresh the Tasks page.

The plugin recognises these sections:

- **Next** — committed next actions
- **Doing** — work currently in progress; the default soft limit is three
- **Waiting** — tasks blocked by someone or something else
- **Later** — uncommitted options, kept visually quiet and folded by default
- **Done** — completed tasks

The `Doing` limit is guidance, not a hard blocker.

### Manage your own areas

Open **Manage areas** to create, rename, or remove areas. Names are normalized consistently, and duplicate normalized names are rejected.

Removing an area never deletes tasks and never changes their workflow status. If tasks use that area, choose either:

- another existing area to reassign them to, or
- **No area** to keep the tasks unassigned.

Clearing an area from affected tasks requires an explicit confirmation.

## Your task file

By default, the plugin reads and writes:

```text
~/tasks.md
```

The file is intentionally simple:

```md
# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-02

## Next

- [ ] Write a proper next action #area:work ! <!-- task:t_example01 -->

## Doing

## Waiting

## Later

## Done
```

- `Areas:` is the board's user-defined area registry; it may also be empty.
- `Doing limit:` controls the soft WIP indicator.
- `#area:<name>` stores a task's optional area.
- `!` stores priority.
- The `<!-- task:... -->` marker is the task's stable ID. Let the plugin create and maintain it.
- Keep the five workflow headings exactly as shown.

### Use an existing Markdown task file

Set `HERMES_TASKS_PATH` **in the environment that starts your Hermes backend**, then restart that backend:

```bash
export HERMES_TASKS_PATH="$HOME/path/to/tasks.md"
```

The plugin never uploads task content. It reads and writes the local file through Hermes' scoped plugin backend.

## Profiles

If you use a named Hermes profile, run the installer with that profile's home as `HERMES_HOME`:

```bash
HERMES_HOME="$HOME/.hermes/profiles/work" ./install.sh
```

Restart the Hermes backend and launch Desktop for the same profile.

## Update

```bash
cd hermes-tasks
git pull
./install.sh
```

The V2 installer detects the earlier `Now / Waiting / Later / Done` format. Before migrating it, the installer creates a timestamped `tasks.md.pre-v2-*.bak` beside the original file. Existing V2 files are left alone.

Fully quit and reopen Desktop whenever `plugin_api.py` changes.

## Uninstall

```bash
hermes plugins disable tasks
rm -rf "${HERMES_HOME:-$HOME/.hermes}/desktop-plugins/tasks"
rm -rf "${HERMES_HOME:-$HOME/.hermes}/plugins/tasks"
```

This does **not** remove your `tasks.md` file.

## Development

The desktop UI is a single uncompiled ESM file. It only imports Hermes' desktop SDK, React, and `react/jsx-runtime`.

```bash
node --check desktop-plugins/tasks/plugin.js
python3 -m unittest discover -s tests -v
```

## Licence

MIT. See [LICENSE](LICENSE).
