from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CONFIG_FILE = "repo-launcher.json"
DEFAULT_SCRIPT_NAME = "RepoLauncher"


@dataclass(frozen=True)
class RepoSpec:
    name: str
    path: Path
    command: tuple[str, ...] = ()


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_command(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(shlex.split(value))
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ValueError("Config commands must be a string or list of strings.")


def infer_command(repo_path: Path) -> tuple[str, ...]:
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            for name in ("start", "dev"):
                if isinstance(scripts.get(name), str):
                    return ("npm", "run", name)

    for candidate in ("app.py", "main.py", "server.py"):
        if (repo_path / candidate).exists():
            return ("python", candidate)

    if (repo_path / "Cargo.toml").exists():
        return ("cargo", "run")
    if (repo_path / "go.mod").exists():
        return ("go", "run", ".")

    return ()


def discover_repos(base_dir: Path) -> dict[str, RepoSpec]:
    repos: dict[str, RepoSpec] = {}
    if not base_dir.exists():
        return repos

    for child in sorted(base_dir.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and (child / ".git").exists():
            repos[child.name] = RepoSpec(
                name=child.name,
                path=child.resolve(),
                command=infer_command(child.resolve()),
            )
    return repos


def merge_repos(base_dir: Path, config: dict) -> dict[str, RepoSpec]:
    repos = discover_repos(base_dir)
    configured = config.get("repos", {})

    if not isinstance(configured, dict):
        raise ValueError("The 'repos' config entry must be an object.")

    for name, raw_spec in configured.items():
        if not isinstance(raw_spec, dict):
            raise ValueError(f"Config for repo '{name}' must be an object.")

        repo_path = Path(raw_spec.get("path", base_dir / name))
        if not repo_path.is_absolute():
            repo_path = (base_dir / repo_path).resolve()
        else:
            repo_path = repo_path.resolve()

        command = normalize_command(raw_spec.get("command")) or infer_command(repo_path)
        repos[name] = RepoSpec(name=name, path=repo_path, command=command)

    return dict(sorted(repos.items(), key=lambda item: item[0].lower()))


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def build_open_command(path: Path, platform_name: str | None = None) -> tuple[str, ...]:
    platform_name = platform_name or current_platform()
    if platform_name == "windows":
        return ("explorer", str(path))
    if platform_name == "macos":
        return ("open", str(path))
    return ("xdg-open", str(path))


def repo_lines(repos: Iterable[RepoSpec]) -> list[str]:
    lines = []
    for repo in repos:
        command = " ".join(repo.command) if repo.command else "open folder"
        lines.append(f"{repo.name}: {repo.path} [{command}]")
    return lines


def run_command(command: tuple[str, ...], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, check=False)
    return completed.returncode


def launch_repo(repo: RepoSpec) -> int:
    if repo.command:
        return run_command(repo.command, repo.path)
    return run_command(build_open_command(repo.path), repo.path)


def desktop_dir() -> Path:
    return Path.home() / "Desktop"


def desktop_script_suffix(platform_name: str) -> str:
    return ".cmd" if platform_name == "windows" else ".sh"


def generate_desktop_script(
    launcher_path: Path,
    destination_dir: Path,
    platform_name: str | None = None,
) -> Path:
    platform_name = platform_name or current_platform()
    destination_dir.mkdir(parents=True, exist_ok=True)
    script_path = destination_dir / f"{DEFAULT_SCRIPT_NAME}{desktop_script_suffix(platform_name)}"

    launcher = str(launcher_path.resolve())
    python_executable = shlex.quote(sys.executable)
    quoted_launcher = shlex.quote(launcher)

    if platform_name == "windows":
        content = "\n".join(
            [
                "@echo off",
                f"python \"{launcher}\" %*",
                "",
            ]
        )
    else:
        content = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"{python_executable} {quoted_launcher} \"$@\"",
                "",
            ]
        )

    script_path.write_text(content, encoding="utf-8")
    if platform_name != "windows":
        script_path.chmod(script_path.stat().st_mode | 0o111)
    return script_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch nearby repositories and apps.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Directory containing sibling repositories.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().with_name(CONFIG_FILE),
        help="Optional JSON config file for repo overrides.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List discovered repositories.")

    for name in ("open", "run", "launch"):
        subparser = subparsers.add_parser(name, help=f"{name.title()} a repository.")
        subparser.add_argument("repo", help="Repository name.")

    desktop_parser = subparsers.add_parser(
        "create-desktop-script",
        help="Create a desktop helper script for this launcher.",
    )
    desktop_parser.add_argument(
        "--destination",
        type=Path,
        default=desktop_dir(),
        help="Directory for the generated script.",
    )
    return parser


def get_repo(repos: dict[str, RepoSpec], name: str) -> RepoSpec:
    if name not in repos:
        available = ", ".join(repos) or "none"
        raise KeyError(f"Unknown repo '{name}'. Available repos: {available}")
    return repos[name]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    base_dir = Path(config.get("base_dir", args.base_dir))
    if not base_dir.is_absolute():
        base_dir = (args.config.parent / base_dir).resolve()
    else:
        base_dir = base_dir.resolve()

    repos = merge_repos(base_dir, config)

    if args.command == "list":
        for line in repo_lines(repos.values()):
            print(line)
        return 0

    if args.command == "create-desktop-script":
        script_path = generate_desktop_script(Path(__file__), args.destination)
        print(script_path)
        return 0

    try:
        repo = get_repo(repos, args.repo)
    except KeyError as error:
        print(error, file=sys.stderr)
        return 1

    if args.command == "open":
        return run_command(build_open_command(repo.path), repo.path)
    if args.command == "run":
        if not repo.command:
            print(f"No runnable command found for {repo.name}.", file=sys.stderr)
            return 1
        return run_command(repo.command, repo.path)
    return launch_repo(repo)


if __name__ == "__main__":
    raise SystemExit(main())
