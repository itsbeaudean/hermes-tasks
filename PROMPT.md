# Install Hermes Tasks with your agent

Copy this into a Hermes session:

> I want to install the Hermes Tasks Desktop plugin from https://github.com/itsbeaudean/hermes-tasks.
>
> Read the repository README and inspect `install.sh`, `desktop-plugins/tasks/plugin.js`, and `plugins/tasks/dashboard/plugin_api.py` before making changes. Confirm that the plugin stores tasks locally in `~/tasks.md` by default, keeps Markdown as the sole persistent store, and does not need permission to override Hermes built-in tools.
>
> If the files look safe, clone the repository into a temporary directory and run its installer. Do not delete or replace an existing `~/tasks.md`. If it uses the earlier V1 headings, verify that the installer creates a timestamped backup before migrating it to V2. Verify that these files were installed under my active `$HERMES_HOME`:
>
> - `desktop-plugins/tasks/plugin.js`
> - `plugins/tasks/dashboard/manifest.json`
> - `plugins/tasks/dashboard/plugin_api.py`
>
> Verify that the `tasks` plugin is enabled and that the backend reports the five V2 workflow sections: Next, Doing, Waiting, Later, and Done. Then tell me to fully quit and reopen Hermes Desktop, and to run **Reload desktop plugins** from the command palette if the Tasks page does not appear.
>
> After it is installed, use the same `tasks.md` file when I ask you to add, complete, organise, or review tasks. Treat areas as user-defined labels rather than fixed workflow categories. Never remove a task when an area is renamed or deleted.
