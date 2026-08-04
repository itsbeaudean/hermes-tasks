from __future__ import annotations

import importlib.util
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "tasks" / "dashboard" / "plugin_api.py"


def load_module():
    assert MODULE_PATH.exists(), "task backend has not been implemented"
    spec = importlib.util.spec_from_file_location("hermes_tasks_plugin_api", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskStoreTests(unittest.TestCase):
    def test_v2_parser_exposes_personal_flow_and_custom_area_metadata(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life, health
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Book dentist #area:health ! <!-- task:t_health01 -->

## Doing

## Waiting

## Later

## Done
"""

        board = api.board_payload(markdown)

        self.assertEqual(list(board["sections"]), ["Next", "Doing", "Waiting", "Later", "Done"])
        task = board["sections"]["Next"][0]
        self.assertEqual(task["id"], "t_health01")
        self.assertEqual(task["title"], "Book dentist")
        self.assertEqual(task["area"], "health")
        self.assertTrue(task["priority"])
        self.assertEqual(board["areas"], ["work", "life", "health"])
        self.assertEqual(board["doing_limit"], 3)

    def test_v2_add_creates_stable_id_and_registers_custom_area(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")

            result = api.TaskStore(path).add(
                "Book dentist",
                section="Next",
                area="health",
                priority=True,
            )

            task = result["sections"]["Next"][0]
            written = path.read_text(encoding="utf-8")
            self.assertRegex(task["id"], r"^t_[a-f0-9]{12}$")
            self.assertEqual(task["title"], "Book dentist")
            self.assertEqual(task["area"], "health")
            self.assertTrue(task["priority"])
            self.assertIn("Areas: work, life, health", written)
            self.assertRegex(
                written,
                r"- \[ \] Book dentist #area:health ! <!-- task:t_[a-f0-9]{12} -->",
            )

    def test_v2_update_moves_and_edits_task_without_changing_its_id(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life, health
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Book dentist #area:health <!-- task:t_dentist001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            revision = store.read()["revision"]

            result = store.update(
                "t_dentist001",
                title="Book dentist appointment",
                section="Doing",
                area="health",
                priority=True,
                revision=revision,
            )

            self.assertEqual(result["sections"]["Next"], [])
            task = result["sections"]["Doing"][0]
            self.assertEqual(task["id"], "t_dentist001")
            self.assertEqual(task["title"], "Book dentist appointment")
            self.assertTrue(task["priority"])

    def test_v2_update_rejects_stale_revision_without_changing_file(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Read book #area:life <!-- task:t_readbook01 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")

            with self.assertRaisesRegex(api.ConflictError, "changed elsewhere"):
                api.TaskStore(path).update(
                    "t_readbook01",
                    section="Doing",
                    revision="stale-revision",
                )

            self.assertEqual(path.read_text(encoding="utf-8"), markdown)

    def test_v2_serializes_mutations_using_the_same_revision(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] First <!-- task:t_first000001 -->
- [ ] Second <!-- task:t_second00001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            revision = store.read()["revision"]
            original_write = store._write
            outcomes = []

            def slow_write(updated):
                time.sleep(0.05)
                original_write(updated)

            store._write = slow_write

            def update(task_id, title):
                try:
                    store.update(task_id, title=title, revision=revision)
                    outcomes.append("saved")
                except api.ConflictError:
                    outcomes.append("conflict")

            threads = [
                threading.Thread(target=update, args=("t_first000001", "First changed")),
                threading.Thread(target=update, args=("t_second00001", "Second changed")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertCountEqual(outcomes, ["saved", "conflict"])
            self.assertEqual(sum(len(tasks) for tasks in store.read()["sections"].values()), 2)

    def test_v2_serializes_same_revision_mutations_across_processes(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Original #area:work <!-- task:t_original001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            revision = api.TaskStore(path).read()["revision"]
            context = multiprocessing.get_context("fork")
            start = context.Event()
            results = context.Queue()

            def worker(title):
                child_api = load_module()

                class SlowWriteStore(child_api.TaskStore):
                    def _write(self, updated):
                        time.sleep(0.2)
                        super()._write(updated)

                start.wait()
                try:
                    SlowWriteStore(path).add(
                        title,
                        section="Next",
                        area="work",
                        revision=revision,
                    )
                    results.put("ok")
                except child_api.ConflictError:
                    results.put("conflict")

            processes = [context.Process(target=worker, args=(title,)) for title in ("Writer A", "Writer B")]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(timeout=5)

            self.assertTrue(all(not process.is_alive() for process in processes))
            outcomes = sorted(results.get(timeout=1) for _ in processes)
            self.assertEqual(outcomes, ["conflict", "ok"])
            titles = [task["title"] for task in api.TaskStore(path).read()["sections"]["Next"]]
            self.assertEqual(len(set(titles) & {"Writer A", "Writer B"}), 1)

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
            [item["title"] for item in board["sections"]["Next"]],
            [
                "Do tax report",
                "Cancel ManyChat",
            ],
        )
        self.assertFalse(board["sections"]["Next"][0]["done"])
        self.assertTrue(board["sections"]["Next"][1]["done"])
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
            added = result["sections"]["Next"][-1]
            self.assertEqual(added["title"], "Ship the task UI")
            self.assertEqual(added["area"], "life")
            self.assertTrue(added["priority"])
            self.assertRegex(written, r"Updated: \d{4}-\d{2}-\d{2}")

    def test_complete_moves_task_to_done_and_adds_completion_date(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-07-31

## Next

- [ ] Do tax report #area:life <!-- task:t_taxreport01 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            self.assertTrue(hasattr(store, "complete"), "complete is not implemented")
            task_id = "t_taxreport01"

            result = store.complete(task_id, True)

            self.assertEqual(result["sections"]["Next"], [])
            completed = result["sections"]["Done"][0]
            self.assertEqual(completed["id"], task_id)
            self.assertTrue(completed["done"])
            self.assertEqual(completed["title"], "Do tax report")
            self.assertRegex(completed["completed_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_v2_delete_removes_only_the_selected_task(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

Keep this note.

## Next

- [ ] Remove me #area:work <!-- task:t_remove0001 -->
- [ ] Keep me #area:life <!-- task:t_keep000001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)

            result = store.delete("t_remove0001", revision=store.read()["revision"])

            self.assertEqual([task["id"] for task in result["sections"]["Next"]], ["t_keep000001"])
            self.assertIn("Keep this note.", path.read_text(encoding="utf-8"))

    def test_v2_update_reorders_task_at_requested_position(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] First <!-- task:t_first000001 -->
- [ ] Second <!-- task:t_second00001 -->
- [ ] Third <!-- task:t_third000001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)

            result = store.update(
                "t_third000001",
                section="Next",
                position=0,
                revision=store.read()["revision"],
            )

            self.assertEqual(
                [task["id"] for task in result["sections"]["Next"]],
                ["t_third000001", "t_first000001", "t_second00001"],
            )

    def test_v2_metadata_edit_preserves_task_position(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] First <!-- task:t_first000001 -->
- [ ] Second <!-- task:t_second00001 -->
- [ ] Third <!-- task:t_third000001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.update(
                "t_second00001",
                priority=True,
                revision=store.read()["revision"],
            )
            self.assertEqual(
                [task["id"] for task in result["sections"]["Next"]],
                ["t_first000001", "t_second00001", "t_third000001"],
            )

    def test_v2_add_to_done_creates_a_completed_task(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.add("Already finished", "Done", revision=store.read()["revision"])
            task = result["sections"]["Done"][0]
            self.assertTrue(task["done"])
            self.assertRegex(task["completed_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_v2_whitespace_section_heading_remains_mutable(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

""" + "## Next   \n" + """
## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            result = api.TaskStore(path).add("Works", "Next")
            self.assertEqual(result["sections"]["Next"][0]["title"], "Works")

    def test_v2_duplicate_ids_fail_closed_and_migration_repairs_them(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] First <!-- task:t_duplicate01 -->
- [ ] Second <!-- task:t_duplicate01 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            with self.assertRaisesRegex(ValueError, "Duplicate task id"):
                store.read()
            migrated = store.migrate()
            ids = [task["id"] for task in migrated["sections"]["Next"]]
            self.assertEqual(len(ids), len(set(ids)))

    def test_v2_board_surfaces_focus_and_wip_signals(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 2

Updated: 2026-08-03

## Next

- [ ] Normal next task #area:life <!-- task:t_normalnext1 -->
- [ ] Priority next task #area:work ! <!-- task:t_priority001 -->

## Doing

- [ ] Active one #area:work <!-- task:t_active0001 -->
- [ ] Active two #area:life <!-- task:t_active0002 -->
- [ ] Active three #area:work <!-- task:t_active0003 -->

## Waiting

- [ ] Waiting response #area:work <!-- task:t_waiting001 -->

## Later

## Done
"""

        board = api.board_payload(markdown)

        self.assertEqual(board["counts_by_section"]["Doing"], 3)
        self.assertEqual(board["focus_task_id"], "t_active0001")
        self.assertEqual(board["next_task_id"], "t_priority001")
        self.assertEqual(
            board["wip"],
            {"count": 3, "limit": 2, "over_limit": True},
        )
        self.assertEqual(board["waiting_count"], 1)

    def test_v2_migration_is_idempotent_and_preserves_existing_tasks(self):
        api = load_module()
        legacy = """# Tasks

Keep this introduction exactly.

Updated: 2026-08-03

## Now

- [ ] Open task #work !
- [x] Already complete #life (completed 2026-08-02)

## Waiting

## Later

## Done

Keep this footer exactly.
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(legacy, encoding="utf-8")
            store = api.TaskStore(path)

            first = store.migrate()
            first_markdown = path.read_text(encoding="utf-8")
            second = store.migrate()

            self.assertIn("Keep this introduction exactly.", first_markdown)
            self.assertIn("Keep this footer exactly.", first_markdown)
            self.assertIn("Areas: work, life", first_markdown)
            self.assertIn("Doing limit: 3", first_markdown)
            self.assertIn("## Next", first_markdown)
            self.assertIn("## Doing", first_markdown)
            self.assertNotIn("## Now", first_markdown)
            self.assertEqual(len(first["sections"]["Next"]), 1)
            self.assertEqual(len(first["sections"]["Done"]), 1)
            self.assertRegex(first_markdown, r"<!-- task:t_[a-f0-9]{12} -->")
            self.assertEqual(path.read_text(encoding="utf-8"), first_markdown)
            self.assertEqual(second["revision"], first["revision"])

    def test_v2_create_area_registers_a_normalized_empty_area(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.create_area("Personal Admin", revision=store.read()["revision"])

            self.assertEqual(result["areas"], ["work", "life", "personal-admin"])
            self.assertIn("Areas: work, life, personal-admin", path.read_text(encoding="utf-8"))

    def test_v2_rename_area_updates_registry_and_every_task_without_changing_ids(self):
        api = load_module()
        markdown = """# Tasks

Keep this prose exactly.

Areas: work, life, health
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Book dentist #area:health <!-- task:t_dentist001 -->

## Doing

- [ ] Exercise #area:health <!-- task:t_exercise001 -->

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.rename_area("health", "Well Being", revision=store.read()["revision"])
            written = path.read_text(encoding="utf-8")

            self.assertEqual(result["areas"], ["work", "life", "well-being"])
            self.assertEqual(
                [task["area"] for section in result["sections"].values() for task in section],
                ["well-being", "well-being"],
            )
            self.assertIn("task:t_dentist001", written)
            self.assertIn("task:t_exercise001", written)
            self.assertIn("Keep this prose exactly.", written)

    def test_v2_rename_area_preserves_checkboxes_outside_managed_sections(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, health
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Managed #area:health <!-- task:t_managed001 -->

## Doing

## Waiting

## Later

## Done

## Notes

- [ ] Unrelated checklist #area:health
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            store.rename_area("health", "wellbeing", revision=store.read()["revision"])
            written = path.read_text(encoding="utf-8")

            self.assertIn("Managed #area:wellbeing", written)
            self.assertIn("Unrelated checklist #area:health", written)

    def test_v2_remove_area_can_reassign_affected_tasks(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life, health
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Book dentist #area:health <!-- task:t_dentist001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.remove_area(
                "health",
                replacement="life",
                revision=store.read()["revision"],
            )

            self.assertEqual(result["areas"], ["work", "life"])
            self.assertEqual(result["sections"]["Next"][0]["area"], "life")
            self.assertIn("task:t_dentist001", path.read_text(encoding="utf-8"))

    def test_v2_remove_area_reassigns_legacy_area_tags(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Legacy personal task #life <!-- task:t_legacy001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.remove_area(
                "life",
                replacement="work",
                revision=store.read()["revision"],
            )
            written = path.read_text(encoding="utf-8")

            self.assertEqual(result["areas"], ["work"])
            self.assertEqual(result["sections"]["Next"][0]["area"], "work")
            self.assertIn("Legacy personal task #area:work", written)
            self.assertNotIn("#life", written)

    def test_v2_area_mutation_preserves_crlf_line_endings(self):
        api = load_module()
        markdown = "\r\n".join(
            [
                "# Tasks",
                "",
                "Areas: work, health",
                "Doing limit: 3",
                "",
                "Updated: 2026-08-03",
                "",
                "## Next",
                "",
                "- [ ] Managed #area:health <!-- task:t_managed001 -->",
                "",
                "## Doing",
                "",
                "## Waiting",
                "",
                "## Later",
                "",
                "## Done",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            for operation in ("create", "rename"):
                with self.subTest(operation=operation):
                    path = Path(directory) / f"{operation}.md"
                    path.write_bytes(markdown.encode("utf-8"))
                    store = api.TaskStore(path)
                    if operation == "create":
                        store.create_area("personal admin", revision=store.read()["revision"])
                        expected = b"Areas: work, health, personal-admin\r\n"
                    else:
                        store.rename_area("health", "wellbeing", revision=store.read()["revision"])
                        expected = b"Areas: work, wellbeing\r\n"
                    written = path.read_bytes()

                    self.assertIn(expected, written)
                    self.assertNotIn(b"\n", written.replace(b"\r\n", b""))

    def test_v2_add_update_and_migration_preserve_crlf_line_endings(self):
        api = load_module()
        v2 = (
            "# Tasks\r\n\r\nAreas: work\r\nDoing limit: 3\r\n\r\n"
            "Updated: 2026-08-03\r\n\r\n## Next\r\n\r\n"
            "- [ ] Existing #area:work <!-- task:t_existing01 -->\r\n\r\n"
            "## Doing\r\n\r\n## Waiting\r\n\r\n## Later\r\n\r\n## Done\r\n"
        )
        legacy = (
            "# Tasks\r\n\r\nUpdated: 2026-08-03\r\n\r\n## Now\r\n\r\n"
            "- [ ] Existing #work\r\n\r\n## Waiting\r\n\r\n## Later\r\n\r\n## Done\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            add_path = root / "add.md"
            add_path.write_bytes(v2.encode("utf-8"))
            api.TaskStore(add_path).add("Added", "Next", area="work")

            update_path = root / "update.md"
            update_path.write_bytes(v2.encode("utf-8"))
            store = api.TaskStore(update_path)
            store.update("t_existing01", title="Changed", revision=store.read()["revision"])

            migrate_path = root / "migrate.md"
            migrate_path.write_bytes(legacy.encode("utf-8"))
            api.TaskStore(migrate_path).migrate()

            for path in (add_path, update_path, migrate_path):
                with self.subTest(operation=path.stem):
                    written = path.read_bytes()
                    self.assertNotIn(b"\n", written.replace(b"\r\n", b""))

    def test_v2_configured_areas_are_normalized_and_deduplicated(self):
        api = load_module()
        markdown = """# Tasks

Areas: Personal Admin, personal-admin, work
Doing limit: 3

Updated: 2026-08-03

## Next
## Doing
## Waiting
## Later
## Done
"""
        self.assertEqual(api.board_payload(markdown)["areas"], ["personal-admin", "work"])

    def test_v2_remove_area_can_clear_tasks_and_remove_default_names(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Personal task #area:life <!-- task:t_personal001 -->

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            result = store.remove_area("life", revision=store.read()["revision"])

            self.assertEqual(result["areas"], ["work"])
            self.assertIsNone(result["sections"]["Next"][0]["area"])
            self.assertNotIn("#area:life", path.read_text(encoding="utf-8"))

    def test_v2_create_area_after_removing_last_area_preserves_doing_limit(self):
        api = load_module()
        markdown = """# Tasks

Areas: life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

## Waiting

## Later

## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(markdown, encoding="utf-8")
            store = api.TaskStore(path)
            removed = store.remove_area("life", revision=store.read()["revision"])
            result = store.create_area("health", revision=removed["revision"])
            written = path.read_text(encoding="utf-8")

            self.assertEqual(result["areas"], ["health"])
            self.assertEqual(result["doing_limit"], 3)
            self.assertIn("Areas: health\nDoing limit: 3", written)

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

Areas: work, life
Doing limit: 3

Updated: 2026-07-31

## Next

## Doing

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
                revision = api.get_board()["revision"]
                added = api.add_task(
                    {
                        "title": "Use the native task page",
                        "section": "Next",
                        "area": "creative",
                        "priority": True,
                        "revision": revision,
                    }
                )
                task_id = added["sections"]["Next"][0]["id"]
                moved = api.update_task(
                    task_id,
                    {"section": "Doing", "revision": added["revision"]},
                )
                completed = api.complete_task(
                    task_id,
                    {"done": True, "revision": moved["revision"]},
                )
                loaded = api.get_board()
            finally:
                if previous is None:
                    os.environ.pop("HERMES_TASKS_PATH", None)
                else:
                    os.environ["HERMES_TASKS_PATH"] = previous

            self.assertEqual(completed["counts"], {"open": 0, "priority": 0, "done": 1})
            self.assertEqual(loaded["sections"]["Done"][0]["id"], completed["sections"]["Done"][0]["id"])
            self.assertIn("creative", loaded["areas"])

    def test_v2_mutation_api_requires_revision_and_real_booleans(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

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
                with self.assertRaises(api.HTTPException) as missing:
                    api.add_task({"title": "Unsafe blind write"})
                self.assertEqual(missing.exception.status_code, 400)

                revision = api.get_board()["revision"]
                with self.assertRaises(api.HTTPException) as invalid_boolean:
                    api.add_task(
                        {
                            "title": "Wrong boolean",
                            "priority": "false",
                            "revision": revision,
                        }
                    )
                self.assertEqual(invalid_boolean.exception.status_code, 400)
            finally:
                if previous is None:
                    os.environ.pop("HERMES_TASKS_PATH", None)
                else:
                    os.environ["HERMES_TASKS_PATH"] = previous

            self.assertNotIn("Unsafe blind write", path.read_text(encoding="utf-8"))
            self.assertNotIn("Wrong boolean", path.read_text(encoding="utf-8"))

    def test_v2_area_api_round_trip_is_revision_safe(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

- [ ] Existing #area:life <!-- task:t_existing001 -->

## Doing

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
                created = api.create_area({"name": "Personal Admin", "revision": api.get_board()["revision"]})
                renamed = api.rename_area(
                    "personal-admin",
                    {"name": "Home", "revision": created["revision"]},
                )
                removed = api.delete_area(
                    "life",
                    revision=renamed["revision"],
                    replacement="home",
                )
            finally:
                if previous is None:
                    os.environ.pop("HERMES_TASKS_PATH", None)
                else:
                    os.environ["HERMES_TASKS_PATH"] = previous

            self.assertEqual(removed["areas"], ["work", "home"])
            self.assertEqual(removed["sections"]["Next"][0]["area"], "home")

    def test_v2_area_api_rejects_non_string_names(self):
        api = load_module()
        markdown = """# Tasks

Areas: work, life
Doing limit: 3

Updated: 2026-08-03

## Next

## Doing

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
                with self.assertRaises(api.HTTPException) as raised:
                    api.create_area({"name": None, "revision": api.get_board()["revision"]})
            finally:
                if previous is None:
                    os.environ.pop("HERMES_TASKS_PATH", None)
                else:
                    os.environ["HERMES_TASKS_PATH"] = previous

            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(path.read_text(encoding="utf-8"), markdown)


if __name__ == "__main__":
    unittest.main()
