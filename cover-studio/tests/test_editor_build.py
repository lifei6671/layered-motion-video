"""正式浏览器编辑器本地构建与页面入口测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as webapp
from editor_build import editor_bundle_stale, ensure_editor_bundle


class EditorBuildTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "fabric-poc" / "src").mkdir(parents=True)
        (self.root / "static").mkdir()
        self.source = self.root / "fabric-poc" / "src" / "main.js"
        self.source.write_text("/* editor */", encoding="utf-8")
        (self.root / "fabric-poc" / "package.json").write_text(
            '{"scripts":{"build":"true"}}', encoding="utf-8"
        )
        (self.root / "fabric-poc" / "package-lock.json").write_text(
            '{"lockfileVersion":3}', encoding="utf-8"
        )
        self.bundle = self.root / "static" / "fabric-poc.bundle.js"

    def tearDown(self):
        self.folder.cleanup()

    def test_missing_stale_and_ready_assets(self):
        self.assertTrue(editor_bundle_stale(self.root))
        self.bundle.write_text("/* compiled editor */", encoding="utf-8")
        now = max(path.stat().st_mtime_ns for path in (
            self.source,
            self.root / "fabric-poc" / "package.json",
            self.root / "fabric-poc" / "package-lock.json"
        ))
        os.utime(self.bundle, ns=(now + 10_000_000, now + 10_000_000))
        self.assertFalse(editor_bundle_stale(self.root))
        with patch("editor_build.subprocess.run") as runner:
            ready, message = ensure_editor_bundle(self.root)
            self.assertTrue(ready)
            self.assertIn("就绪", message)
            runner.assert_not_called()
        os.utime(self.source, ns=(now + 20_000_000, now + 20_000_000))
        self.assertTrue(editor_bundle_stale(self.root))

    def test_missing_node_produces_actionable_message(self):
        with patch("editor_build.shutil.which", return_value=None):
            ready, message = ensure_editor_bundle(self.root)
        self.assertFalse(ready)
        self.assertIn("Node.js", message)

    def test_missing_frontend_dependency_triggers_install_and_build(self):
        from subprocess import CompletedProcess

        operations = []

        def execute(argv, **kwargs):
            operations.append((argv, kwargs["cwd"]))
            if "ci" in argv:
                for module in ("fabric", "esbuild"):
                    (self.root / "fabric-poc" / "node_modules" / module).mkdir(
                        parents=True, exist_ok=True
                    )
            elif "build" in argv:
                self.bundle.write_text("/* newly compiled */", encoding="utf-8")
            return CompletedProcess(argv, 0, stdout="ok", stderr="")

        with patch("editor_build.shutil.which", return_value="npm.cmd"), patch(
            "editor_build.subprocess.run", side_effect=execute
        ):
            ready, message = ensure_editor_bundle(self.root)
        self.assertTrue(ready, message)
        self.assertTrue(self.bundle.is_file())
        self.assertEqual(len(operations), 2)
        self.assertIn("ci", operations[0][0])
        self.assertIn("build", operations[1][0])

    def test_dependency_install_failure_preserves_compatibility(self):
        from subprocess import CompletedProcess

        with patch("editor_build.shutil.which", return_value="npm.cmd"), patch(
            "editor_build.subprocess.run",
            return_value=CompletedProcess(["npm", "ci"], 2, "", "依赖安装异常")
        ):
            ready, message = ensure_editor_bundle(self.root)
        self.assertFalse(ready)
        self.assertIn("执行失败", message)
        self.assertFalse(self.bundle.exists())
        self.assertEqual(webapp.app.test_client().get("/legacy").status_code, 200)

    def test_homepage_without_built_bundle_shows_build_instructions(self):
        with patch.object(webapp, "BASE_DIR", self.root):
            result = webapp.app.test_client().get("/")
        self.assertEqual(result.status_code, 503)
        self.assertIn("Node.js", result.get_data(as_text=True))
        self.assertIn('href="/legacy"', result.get_data(as_text=True))
        self.assertEqual(webapp.app.test_client().get("/legacy").status_code, 200)


if __name__ == "__main__":
    unittest.main()
