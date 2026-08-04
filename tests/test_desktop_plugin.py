from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "desktop-plugins" / "tasks" / "plugin.js"
README_PATH = Path(__file__).resolve().parents[1] / "README.md"


class DesktopPluginTests(unittest.TestCase):
    def test_native_tasks_v2_plugin_has_valid_disk_plugin_shape(self):
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
        self.assertIn("const SECTION_ORDER = ['Next', 'Doing', 'Waiting', 'Done']", source)
        self.assertIn("const LATER_SECTION = 'Later'", source)
        self.assertIn("draggable: task.section !== 'Done'", source)
        self.assertIn("dataTransfer.setData('text/plain'", source)
        self.assertIn("section === 'Done' ? {} : { position }", source)
        self.assertIn("canonicalTasks.findIndex", source)
        self.assertIn("sourcePosition", source)
        self.assertIn("await queryClient.cancelQueries({ queryKey: QUERY_KEY })", source)
        self.assertIn("queryClient.invalidateQueries({ queryKey: QUERY_KEY })", source)
        self.assertIn("method: 'PATCH'", source)
        self.assertIn("method: 'DELETE'", source)
        self.assertIn("revision", source)
        self.assertIn("board.areas", source)
        self.assertIn("doing_limit", source)
        self.assertIn("Ask Hermes", source)
        self.assertIn("prompt.submit", source)
        self.assertIn("DialogDescription", source)
        self.assertIn("group-focus-within:opacity-100", source)
        self.assertIn("collapsedSections", source)
        self.assertIn("onToggleCollapsed", source)
        self.assertIn("aria-expanded", source)
        self.assertIn("[writing-mode:vertical-rl]", source)
        self.assertIn("function AreaManager", source)
        self.assertIn("Manage areas", source)
        self.assertIn("request('/areas'", source)
        self.assertIn("replacement", source)
        self.assertIn("renameAreaLocally", source)
        self.assertIn("removeAreaLocally", source)
        self.assertGreaterEqual(source.count("await queryClient.cancelQueries({ queryKey: QUERY_KEY })"), 4)
        self.assertIn("areaMutation.mutateAsync", source)
        self.assertIn("let requestStarted = false", source)
        self.assertIn("if (!requestStarted)", source)
        self.assertIn("if (saved)", source)
        self.assertIn("Confirm clear & remove", source)
        self.assertIn("function dropPosition", source)
        self.assertIn("sourcePosition < targetPosition", source)
        self.assertIn("event.key === '/'", source)
        self.assertIn("event.key.toLowerCase() === 'n'", source)
        self.assertNotRegex(source.lower(), r"\bdemo\b")
        self.assertNotIn("SegmentedControl", source)
        result = subprocess.run(
            ["node", "--check", str(PLUGIN_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_area_operations_and_drop_positions_preserve_board_semantics(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        helpers = source[source.index("const SECTION_ORDER"):source.index("function useBoard")]
        assertions = r"""
const sections = emptySections()
sections.Next.push({ id: 'a', title: 'Plan', section: 'Next', area: 'work', priority: false, done: false })
sections.Doing.push({ id: 'b', title: 'Build', section: 'Doing', area: 'creative', priority: true, done: false })
sections.Later.push({ id: 'c', title: 'Consider', section: 'Later', area: 'life', priority: false, done: false })
const original = recalculateBoard({ sections, areas: ['work', 'creative', 'life'], doing_limit: 3, revision: 'test' })
const originalJson = JSON.stringify(original)
const created = createAreaLocally(original, '  Client Success  ')
if (!created.areas.includes('client-success')) throw new Error('custom area was not normalized')
if (JSON.stringify(original) !== originalJson) throw new Error('area creation mutated its input')

let duplicateRejected = false
try { createAreaLocally(created, 'CLIENT SUCCESS') } catch (_error) { duplicateRejected = true }
if (!duplicateRejected) throw new Error('duplicate normalized area was accepted')

const renamed = renameAreaLocally(created, 'work', 'Business Ops')
if (renamed.areas.includes('work') || !renamed.areas.includes('business-ops')) throw new Error('area registry rename failed')
const renamedTasks = ALL_SECTIONS.flatMap(section => renamed.sections[section])
if (renamedTasks.some(task => task.area === 'work')) throw new Error('task area rename failed')
if (renamedTasks.length !== 3) throw new Error('rename changed the task count')

const reassigned = removeAreaLocally(renamed, 'life', 'business-ops')
const reassignedTasks = ALL_SECTIONS.flatMap(section => reassigned.sections[section])
if (reassignedTasks.some(task => task.area === 'life')) throw new Error('area reassignment failed')
if (reassignedTasks.length !== 3) throw new Error('reassignment changed the task count')

const cleared = removeAreaLocally(reassigned, 'creative', null)
const clearedTasks = ALL_SECTIONS.flatMap(section => cleared.sections[section])
if (clearedTasks.some(task => task.area === 'creative')) throw new Error('area clear failed')
if (!clearedTasks.some(task => task.area === null)) throw new Error('area clear did not preserve unassigned tasks')
if (clearedTasks.length !== 3) throw new Error('area clear changed the task count')

const cards = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]
if (dropPosition(cards, 'a', 'd') !== 2) throw new Error('forward drop position is wrong')
if (dropPosition(cards, 'd', 'b') !== 1) throw new Error('backward drop position is wrong')
"""
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", helpers + assertions],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_readme_does_not_advertise_the_private_demo(self):
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(readme.lower(), r"\bdemo\b")
        self.assertNotIn("hermes-tasks-v2-demo", readme)


if __name__ == "__main__":
    unittest.main()
