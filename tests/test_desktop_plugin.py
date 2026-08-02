from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "desktop-plugins" / "tasks" / "plugin.js"


class DesktopPluginTests(unittest.TestCase):
    def test_native_tasks_plugin_has_valid_disk_plugin_shape(self):
        self.assertTrue(PLUGIN_PATH.exists(), "desktop task plugin is not implemented")
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", source)
        self.assertTrue(imports)
        self.assertEqual(
            set(imports) - {"@hermes/plugin-sdk", "react", "react/jsx-runtime"},
            set(),
        )
        self.assertIn("id: ID", source)
        self.assertIn("ROUTES_AREA", source)
        self.assertIn("SIDEBAR_NAV_AREA", source)
        self.assertIn("STATUSBAR_AREAS", source)
        self.assertNotIn("action: jsx(Button", source, "ErrorState actions must use children")
        self.assertIn("DEMO_TASKS", source)
        self.assertIn("{ id: 'demo', label: 'Demo' }", source)
        self.assertIn("Ship the native task dashboard", source)
        result = subprocess.run(
            ["node", "--check", str(PLUGIN_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
