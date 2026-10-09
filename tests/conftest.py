"""Shared fixtures: a recording environment, git checkout builders, agent factory."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

import pytest
from harbor.environments.base import ExecResult

from harbor_omp import OmpAgent

#: The model every test trial runs; provider/model, as Harbor requires.
MODEL = "openrouter/deepseek/deepseek-v4-flash"


class RecordingEnvironment:
    """A ``BaseEnvironment`` stand-in that records and runs nothing.

    ``sequence`` interleaves uploads and execs in call order, so a test can
    assert that something was recorded *before* something else ran (the argv
    record before the agent launch, the home reset before the config extract).
    """

    def __init__(self, stdout: str = "") -> None:
        self.uploads: list[tuple[Path, str]] = []
        self.uploaded: dict[str, bytes] = {}
        self.execs: list[dict[str, object]] = []
        self.sequence: list[tuple[str, str]] = []
        self.stdout = stdout

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        source = Path(source_path)
        self.uploads.append((source, target_path))
        self.uploaded[target_path] = source.read_bytes()
        self.sequence.append(("upload", target_path))

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        self.execs.append(
            {"command": command, "user": user, "env": env, "cwd": cwd}
        )
        self.sequence.append(("exec", command))
        return ExecResult(return_code=0, stdout=self.stdout)

    @property
    def commands(self) -> list[str]:
        return [str(entry["command"]) for entry in self.execs]

    def commands_matching(self, needle: str) -> list[str]:
        return [command for command in self.commands if needle in command]

    def uploads_matching(self, needle: str) -> list[str]:
        return [target for _, target in self.uploads if needle in target]

    def index_of_first(self, kind: str, needle: str) -> int:
        """The position in ``sequence`` of the first ``kind`` entry containing needle."""

        for index, (entry_kind, value) in enumerate(self.sequence):
            if entry_kind == kind and needle in value:
                return index
        raise AssertionError(f"no {kind} containing {needle!r} in {self.sequence!r}")


def git(repo: Path, *args: str) -> str:
    """Run one git command in ``repo`` and return its stdout, stripped."""

    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit_checkout(repo: Path, message: str = "fixture") -> str:
    """Make ``repo`` a clean one-commit git checkout; return its HEAD."""

    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "harbor-omp tests")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def make_agent(tmp_path: Path):
    """Build an ``OmpAgent`` with test defaults; keyword arguments override them."""

    def _make(**options: object) -> OmpAgent:
        arguments: dict[str, object] = {
            "logs_dir": tmp_path / "logs",
            "model_name": MODEL,
            "environment_logs_dir": PurePosixPath("/logs/agent"),
        }
        arguments.update(options)
        return OmpAgent(**arguments)

    return _make


@pytest.fixture
def plugin_repo(tmp_path: Path) -> tuple[Path, str]:
    """A clean one-commit plugin checkout: (repo, HEAD sha)."""

    repo = tmp_path / "plugin-src"
    repo.mkdir()
    (repo / "index.ts").write_bytes(b"export const name = 'demo-plugin';\n")
    return repo, commit_checkout(repo, "plugin")


@pytest.fixture
def config_repo(tmp_path: Path) -> tuple[Path, str]:
    """A clean checkout laid out like a config dir: (repo, HEAD sha)."""

    repo = tmp_path / "omp-config-src"
    agent = repo / "agent"
    for relpath in (
        "AGENTS.md",
        "rules/uv-not-pip.md",
        "skills/duckdb/SKILL.md",
        "hooks/pre/__tests__/command-guard.test.ts",
    ):
        path = agent / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relpath}\n", encoding="utf-8")
    return repo, commit_checkout(repo, "config")
