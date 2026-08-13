import json
import tempfile
import unittest
from pathlib import Path

import launcher


class LauncherTests(unittest.TestCase):
    def test_discover_repos_finds_git_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "alpha" / ".git").mkdir(parents=True)
            (base_dir / "beta").mkdir()

            repos = launcher.discover_repos(base_dir)

            self.assertEqual(list(repos), ["alpha"])
            self.assertEqual(repos["alpha"].path, (base_dir / "alpha").resolve())

    def test_infer_command_prefers_package_json_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"dev": "vite", "start": "node server.js"}}),
                encoding="utf-8",
            )

            self.assertEqual(launcher.infer_command(repo), ("npm", "run", "start"))

    def test_merge_repos_applies_config_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "alpha" / ".git").mkdir(parents=True)
            custom = base_dir / "custom"
            custom.mkdir()
            (custom / "main.py").write_text("print('hello')\n", encoding="utf-8")

            repos = launcher.merge_repos(
                base_dir,
                {
                    "repos": {
                        "alpha": {"command": "python app.py"},
                        "custom": {"path": str(custom)},
                    }
                },
            )

            self.assertEqual(repos["alpha"].command, ("python", "app.py"))
            self.assertEqual(repos["custom"].command, ("python", "main.py"))

    def test_generate_desktop_script_creates_shell_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script = launcher.generate_desktop_script(
                Path("/tmp/launcher.py"),
                Path(temp_dir),
                platform_name="linux",
            )

            content = script.read_text(encoding="utf-8")

            self.assertTrue(script.exists())
            self.assertIn("python", content)
            self.assertIn("/tmp/launcher.py", content)

    def test_repo_lines_include_commands(self) -> None:
        repos = [
            launcher.RepoSpec("alpha", Path("/repos/alpha"), ("python", "main.py")),
            launcher.RepoSpec("beta", Path("/repos/beta")),
        ]

        lines = launcher.repo_lines(repos)

        self.assertIn("alpha: /repos/alpha [python main.py]", lines[0])
        self.assertIn("beta: /repos/beta [open folder]", lines[1])


if __name__ == "__main__":
    unittest.main()
