# Hermes Tasks

A small, local task board for Hermes Desktop.

It adds a **Tasks** page in the sidebar and a compact task count in the status bar. Tasks live in a normal Markdown file, so there is no account, hosted database, or separate task app to maintain.

![Hermes Desktop plugin](https://img.shields.io/badge/Hermes-Desktop%20plugin-6d5efc)

## What it does

- Shows `Now`, `Waiting`, `Later`, and `Done` sections
- Adds tasks from inside Hermes Desktop
- Completes and reopens tasks
- Filters tasks by priority, work, or life
- Keeps the source of truth in one local `tasks.md` file
- Adds a safe demo mode for screenshots and testing

## Install

**Requirements:** Hermes Desktop and the Hermes CLI must already be installed.

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

Fully quit and reopen Hermes Desktop after installation so its backend mounts the task API. If your Desktop app uses a separate gateway, run `hermes gateway restart` instead. If **Tasks** does not appear in the sidebar within a few seconds, open the command palette and run **Reload desktop plugins**.

## How to use it

Open **Tasks** from the Hermes Desktop sidebar. The small count in the status bar also opens the page.

1. Type a concrete next action into the field at the top and select **Add**. New tasks start in **Now**.
2. Tick a task to move it to **Done**. Untick it to return it to **Now**.
3. Use the filters to show priority, work, or life tasks. Add `!`, `#work`, or `#life` to the task text to use those filters.
4. Edit the Markdown file directly whenever you prefer. Refresh the Tasks page to reload it.

The plugin recognises these sections:

- **Now** — tasks you can act on next
- **Waiting** — tasks blocked by someone or something else
- **Later** — tasks you want to keep without treating as active work
- **Done** — completed tasks

## Your task file

By default, the plugin reads and writes:

```text
~/tasks.md
```

The file is intentionally simple:

```md
# Tasks

Updated: 2026-08-02

## Now

- [ ] Write a proper next action #work !

## Waiting

## Later

## Done
```

- Add `!` at the end of a task to mark it as priority.
- Add `#work` or `#life` to use the built-in filters.
- Keep the four headings exactly as shown.

### Use an existing Markdown task file

Set `HERMES_TASKS_PATH` **in the environment that starts your Hermes gateway**, then restart the gateway:

```bash
export HERMES_TASKS_PATH="$HOME/path/to/tasks.md"
```

The plugin never uploads task content. It reads and writes the local file through Hermes' scoped plugin backend.

## Profiles

If you use a named Hermes profile, run the installer with that profile's home as `HERMES_HOME`:

```bash
HERMES_HOME="$HOME/.hermes/profiles/work" ./install.sh
```

Restart the gateway and launch Desktop for the same profile.

## Update

```bash
cd hermes-tasks
git pull
./install.sh
```

Restart the gateway whenever `plugin_api.py` changes.

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
