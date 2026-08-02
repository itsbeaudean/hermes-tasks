from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "tasks"
    / "dashboard"
    / "plugin_api.py"
)


def load_module():
    assert MODULE_PATH.exists(), "task backend has not been implemented"
    spec = importlib.util.spec_from_file_location("hermes_tasks_plugin_api", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskStoreTests(unittest.TestCase):
    def test_parse_preserves_sections_and_task_text(self):
        api = load_module()
        markdown = """# Tasks

Updated: 2026-07-31

## Now

- [ ] Do tax report #life
- [x] Cancel ManyChat #work (completed 2026-07-31)

## Waiting

- [ ] Confirm replies #work !
"""

        board = api.parse_board(markdown)

        self.assertEqual(
            [item["title"] for item in board["sections"]["Now"]],
            [
                "Do tax report #life",
                "Cancel ManyChat #work (completed 2026-07-31)",
            ],
        )
        self.assertFalse(board["sections"]["Now"][0]["done"])
        self.assertTrue(board["sections"]["Now"][1]["done"])
        self.assertTrue(board["sections"]["Waiting"][0]["priority"])
        self.assertEqual(board["sections"]["Waiting"][0]["area"], "work")

    def test_add_inserts_into_section_without_rewriting_surrounding_markdown(self):
        api = load_module()
        self.assertTrue(hasattr(api, "TaskStore"), "TaskStore is not implemented")
        markdown = """# Tasks

Keep this prose exactly.

Updated: 2026-07-31

## Now

- [ ] Existing task #life

## Waiting

- [ ] External reply #work
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")

            result = api.TaskStore(path).add("Ship the task UI #life !", "Now")

            written = path.read_text(encoding="utf-8")
            self.assertIn("Keep this prose exactly.", written)
            self.assertIn(
                "- [ ] Existing task #life\n- [ ] Ship the task UI #life !\n\n## Waiting",
                written,
            )
            self.assertEqual(result["sections"]["Now"][-1]["title"], "Ship the task UI #life !")
            self.assertRegex(written, r"Updated: \d{4}-\d{2}-\d{2}")

    def test_complete_moves_task_to_done_and_adds_completion_date(self):
        api = load_module()
        markdown = """# Tasks

Updated: 2026-07-31

## Now

- [ ] Do tax report #life

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            self.assertTrue(hasattr(store, "complete"), "complete is not implemented")
            task_id = api.parse_board(markdown)["sections"]["Now"][0]["id"]

            result = store.complete(task_id, True)

            self.assertEqual(result["sections"]["Now"], [])
            completed = result["sections"]["Done"][0]
            self.assertTrue(completed["done"])
            self.assertRegex(
                completed["title"],
                r"^Do tax report #life \(completed \d{4}-\d{2}-\d{2}\)$",
            )

    def test_read_returns_counts_and_revision_that_changes_with_file(self):
        api = load_module()
        markdown = """# Tasks

Updated: 2026-07-31

## Now

- [ ] Priority task #work !
- [ ] Normal task #life

## Waiting

## Later

## Done

- [x] Finished #work (completed 2026-07-30)
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            self.assertTrue(hasattr(store, "read"), "read is not implemented")

            first = store.read()
            path.write_text(markdown.replace("Normal task", "Changed task"), encoding="utf-8")
            second = store.read()

            self.assertEqual(first["counts"], {"open": 2, "priority": 1, "done": 1})
            self.assertNotEqual(first["revision"], second["revision"])

    def test_api_functions_round_trip_against_configured_task_file(self):
        api = load_module()
        self.assertTrue(hasattr(api, "get_board"), "GET endpoint is not implemented")
        markdown = """# Tasks

Updated: 2026-07-31

## Now

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            previous = os.environ.get("HERMES_TASKS_PATH")
            os.environ["HERMES_TASKS_PATH"] = str(path)
            try:
                added = api.add_task({"title": "Use the native task page #life", "section": "Now"})
                task_id = added["sections"]["Now"][0]["id"]
                completed = api.complete_task(task_id, {"done": True})
                loaded = api.get_board()
            finally:
                if previous is None:
                    os.environ.pop("HERMES_TASKS_PATH", None)
                else:
                    os.environ["HERMES_TASKS_PATH"] = previous

            self.assertEqual(completed["counts"], {"open": 0, "priority": 0, "done": 1})
            self.assertEqual(loaded["sections"]["Done"][0]["id"], completed["sections"]["Done"][0]["id"])


if __name__ == "__main__":
    unittest.main()
