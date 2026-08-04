from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "install.sh"


class InstallerTests(unittest.TestCase):
    def _run_installer(self, root: Path, task_file: Path) -> None:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        hermes = bin_dir / "hermes"
        hermes.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hermes.chmod(0o755)
        home = root / "home"
        home.mkdir()
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "HOME": str(home),
            "HERMES_HOME": str(home / ".hermes"),
            "HERMES_TASKS_PATH": str(task_file),
        }
        subprocess.run(
            [str(INSTALLER)],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_existing_v2_file_with_now_in_prose_is_left_unchanged(self):
        markdown = """# Tasks

Areas: personal-admin
Doing limit: 3

Updated: 2026-08-03

Old documentation called the first lane `## Now`.

## Next

- [ ] Existing #area:personal-admin <!-- task:t_existing01 -->

## Doing
## Waiting
## Later
## Done
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_file = root / "tasks.md"
            task_file.write_text(markdown, encoding="utf-8")

            self._run_installer(root, task_file)

            self.assertEqual(task_file.read_text(encoding="utf-8"), markdown)
            self.assertEqual(list(root.glob("tasks.md.pre-v2-*.bak")), [])

    def test_v1_migration_creates_backup_and_preserves_crlf(self):
        markdown = (
            "# Tasks\r\n\r\nUpdated: 2026-08-03\r\n\r\n## Now\r\n\r\n"
            "- [ ] Existing #work\r\n\r\n## Waiting\r\n\r\n## Later\r\n\r\n## Done\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task_file = root / "tasks.md"
            original = markdown.encode("utf-8")
            task_file.write_bytes(original)

            self._run_installer(root, task_file)

            backups = list(root.glob("tasks.md.pre-v2-*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            migrated = task_file.read_bytes()
            self.assertNotIn(b"\n", migrated.replace(b"\r\n", b""))
            self.assertIn(b"## Next\r\n", migrated)
            self.assertIn(b"## Doing\r\n", migrated)


if __name__ == "__main__":
    unittest.main()
