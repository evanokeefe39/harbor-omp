"""Capability closers: resume, load native, skills, MCP, handoff.

Tests drive OmpAgent methods that are exercised from the base class:
- resume(): sets _resume, calls run(); with install_only the argv is recorded
- load(): sets _load, calls run(); seeds the session dir via _upload_load_trajectory
- _config_home_command(): includes skills copy and MCP JSON write when configured
- handoff(): classmethod that copies a session and returns argv

Each test uses a RecordingEnvironment that records execs/uploads without running
a real container, or a ShellEnvironment that runs a real POSIX shell.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest
from conftest import RecordingEnvironment
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.environments.base import ExecResult
from harbor.models.task.config import MCPServerConfig

from harbor_omp import OmpAgent

MODEL = "openrouter/deepseek/deepseek-v4-flash"


def _posix_shell() -> str:
    """Git Bash on Windows (WSL's bash cannot see Windows temp paths)."""

    if os.name == "nt":
        programs = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        git_bash = programs / "Git" / "bin" / "bash.exe"
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    assert found, "the capability tests need a POSIX shell (bash)"
    return found


class ShellEnvironment:
    """A ``BaseEnvironment`` stand-in that runs every exec in a real shell.

    Preloads an ``omp`` stub and ``bun`` stub so that the config-home command
    can run without the real CLI installed.
    """

    def __init__(self, omp_version: str = "omp/18.6.0") -> None:
        self.prelude = (
            "omp() {\n"
            '  case "$1" in\n'
            "    --version) printf '%s\\n' 'omp/18.6.0';;\n"
            "    *) return 0;;\n"
            "  esac\n"
            "}\n"
            "bun() {\n:\n}\n"
        )
        self.execs: list[dict[str, object]] = []
        self.uploads: list[tuple[Path, str]] = []

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        self.uploads.append((Path(source_path), target_path))

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        self.execs.append({"command": command, "user": user, "env": env, "cwd": cwd})
        shell_env = dict(os.environ, PATH="/usr/bin:/bin", HOME="/tmp")
        done = subprocess.run(
            [_posix_shell(), "-c", self.prelude + command],
            capture_output=True,
            text=True,
            env=shell_env,
            timeout=60,
            check=False,
        )
        return ExecResult(return_code=done.returncode, stdout=done.stdout, stderr=done.stderr)

    @property
    def commands(self) -> list[str]:
        return [str(entry["command"]) for entry in self.execs]


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_resume_adds_continue_flag(make_agent) -> None:
    """With _resume set, the argv contains --continue."""
    agent = make_agent(install_only=True)
    agent._resume = True
    argv, _ = agent._run_argv("do it")
    assert "--continue" in argv


def test_resume_without_flag_no_continue(make_agent) -> None:
    """Without _resume, the argv does NOT contain --continue."""
    agent = make_agent(install_only=True)
    argv, _ = agent._run_argv("do it")
    assert "--continue" not in argv


# ---------------------------------------------------------------------------
# Load native trajectory
# ---------------------------------------------------------------------------


def test_load_adds_resume_flag_and_stem(make_agent, tmp_path: Path) -> None:
    """With _load and _load_stem set, argv contains --resume <stem>."""
    agent = make_agent(install_only=True)
    agent._load = True
    agent._load_stem = "session-abc123"
    argv, _ = agent._run_argv("do it")
    assert "--resume" in argv
    idx = argv.index("--resume")
    assert argv[idx + 1] == "session-abc123"


def test_load_without_a_seeded_stem_adds_no_resume(make_agent) -> None:
    """_load with no stem must not emit a bare --resume (it would swallow the
    instruction as the session id, and a None slot cannot be quoted)."""
    agent = make_agent(install_only=True)
    agent._load = True
    argv, _ = agent._run_argv("do it")
    assert "--resume" not in argv


def test_upload_load_trajectory_uploads_to_session_dir(make_agent, tmp_path: Path) -> None:
    """_upload_load_trajectory uploads the source into the container session dir."""
    source = tmp_path / "session.jsonl"
    source.write_text('{"type":"session","id":"s1"}\n', encoding="utf-8")
    agent = make_agent(environment_logs_dir=PurePosixPath("/logs/agent"))
    env = RecordingEnvironment()
    asyncio.run(agent._upload_load_trajectory(env, source))
    # The target should be under the session dir
    matching = env.uploads_matching("/logs/agent/omp-sessions/")
    assert len(matching) == 1


def test_validate_native_load_trajectory_valid(tmp_path: Path) -> None:
    """A valid omp session JSONL is accepted."""
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"type":"session","id":"s1"}\n{"type":"message","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
        encoding="utf-8",
    )
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    agent._validate_native_load_trajectory(path)  # no raise


def test_validate_native_load_trajectory_invalid_json(tmp_path: Path) -> None:
    """A file with non-JSON content is rejected."""
    path = tmp_path / "session.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    with pytest.raises(ValueError, match="is not JSON"):
        agent._validate_native_load_trajectory(path)


def test_validate_native_load_trajectory_wrong_type_first_line(tmp_path: Path) -> None:
    """First line must have type=session."""
    path = tmp_path / "session.jsonl"
    path.write_text('{"type":"message","id":"m1"}\n', encoding="utf-8")
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    with pytest.raises(ValueError, match="first object must have"):
        agent._validate_native_load_trajectory(path)


def test_validate_native_load_trajectory_blank(tmp_path: Path) -> None:
    """A blank file is rejected."""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    with pytest.raises(ValueError, match="blank"):
        agent._validate_native_load_trajectory(path)


def test_validate_native_load_trajectory_rejects_a_non_jsonl_name(tmp_path: Path) -> None:
    """omp resolves --resume <stem> by .jsonl filename in the session dir, so a
    differently-named file would upload and then never be found."""
    path = tmp_path / "session.dat"
    path.write_text('{"type":"session","id":"s1"}\n', encoding="utf-8")
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    with pytest.raises(ValueError, match="expected a .jsonl file"):
        agent._validate_native_load_trajectory(path)


# ---------------------------------------------------------------------------
# Skills in config-home command
# ---------------------------------------------------------------------------


def test_config_home_skills_copy_when_skills_dir_set() -> None:
    """With skills_dir set, the config-home command includes a cp into agent/skills/."""
    agent = OmpAgent(
        logs_dir=Path("/tmp/logs"),
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        skills_dir="/tmp/skillsrc",
    )
    cmd = agent._config_home_command()
    assert "agent/skills/" in cmd
    assert "/tmp/skillsrc/*" in cmd


def test_config_home_no_skills_when_unset() -> None:
    """Without skills_dir, no skills copy in the config-home command."""
    agent = OmpAgent(
        logs_dir=Path("/tmp/logs"),
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
    )
    cmd = agent._config_home_command()
    assert "agent/skills/" not in cmd


def test_config_home_skills_in_real_shell_with_valid_dir(tmp_path: Path) -> None:
    """Skills copy works in a real shell with a valid skills_dir."""
    skills_root = tmp_path / "skillsrc"
    (skills_root / "pdf").mkdir(parents=True)
    (skills_root / "pdf" / "SKILL.md").write_text("# PDF skill\n", encoding="utf-8")
    (skills_root / "git").mkdir(parents=True)
    (skills_root / "git" / "SKILL.md").write_text("# Git skill\n", encoding="utf-8")

    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
        skills_dir=str(skills_root),
    )
    env = ShellEnvironment()
    asyncio.run(agent._prepare_config_home(env))

    config_dir = tmp_path / "omp-home" / ".omp"
    skills_dir = config_dir / "agent" / "skills"
    assert (skills_dir / "pdf" / "SKILL.md").read_text(encoding="utf-8") == "# PDF skill\n"
    assert (skills_dir / "git" / "SKILL.md").read_text(encoding="utf-8") == "# Git skill\n"


def test_config_home_skills_missing_dir_fails(tmp_path: Path) -> None:
    """A missing or unreadable skills_dir fails the config-home step loudly."""
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
        skills_dir=str(tmp_path / "nonexistent-skills"),
    )
    env = ShellEnvironment()
    with pytest.raises(NonZeroAgentExitCodeError):
        asyncio.run(agent._prepare_config_home(env))


def test_config_home_skills_empty_dir_fails(tmp_path: Path) -> None:
    """An empty skills_dir fails too: nothing to copy is a config bug, not a
    silent no-op (a skills_dir is only set when skills were meant to arrive)."""
    source = tmp_path / "skillsrc"
    source.mkdir()
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
        skills_dir=str(source),
    )
    env = ShellEnvironment()
    with pytest.raises(NonZeroAgentExitCodeError):
        asyncio.run(agent._prepare_config_home(env))


# ---------------------------------------------------------------------------
# MCP servers in config-home command
# ---------------------------------------------------------------------------


def test_config_home_mcp_writes_json_when_configured(tmp_path: Path) -> None:
    """With mcp_servers, the config-home step writes agent/mcp.json."""
    server = MCPServerConfig(
        name="my-server",
        transport="stdio",
        command="npx",
        args=["@modelcontextprotocol/server-filesystem", "/tmp"],
    )
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
        mcp_servers=[server],
    )
    env = ShellEnvironment()
    asyncio.run(agent._prepare_config_home(env))

    mcp_path = tmp_path / "omp-home" / ".omp" / "agent" / "mcp.json"
    assert mcp_path.is_file()
    parsed = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "mcpServers" in parsed
    assert parsed["mcpServers"]["my-server"]["type"] == "stdio"
    assert parsed["mcpServers"]["my-server"]["command"] == "npx"


def test_config_home_mcp_http_servers(tmp_path: Path) -> None:
    """HTTP/sse server entries are written with type=http and url."""
    server = MCPServerConfig(
        name="remote-server",
        transport="streamable-http",
        url="https://mcp.example.com/sse",
    )
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
        mcp_servers=[server],
    )
    env = ShellEnvironment()
    asyncio.run(agent._prepare_config_home(env))

    mcp_path = tmp_path / "omp-home" / ".omp" / "agent" / "mcp.json"
    parsed = json.loads(mcp_path.read_text(encoding="utf-8"))
    entry = parsed["mcpServers"]["remote-server"]
    assert entry["type"] == "http"
    assert entry["url"] == "https://mcp.example.com/sse"


def test_config_home_no_mcp_when_empty(tmp_path: Path) -> None:
    """Without mcp_servers, no mcp.json is written."""
    agent = OmpAgent(
        logs_dir=tmp_path / "logs",
        model_name=MODEL,
        environment_logs_dir=PurePosixPath("/logs/agent"),
        config_home=str(tmp_path / "omp-home"),
    )
    env = ShellEnvironment()
    asyncio.run(agent._prepare_config_home(env))

    mcp_path = tmp_path / "omp-home" / ".omp" / "agent" / "mcp.json"
    assert not mcp_path.exists()


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


def test_handoff_requires_omp_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """handoff raises ValueError when omp is not found."""
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ValueError, match="omp CLI not found on PATH"):
        OmpAgent.handoff(Path("/tmp/trial"), Path("/tmp/cwd"))


def test_handoff_requires_exactly_one_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """handoff raises ValueError when no session or multiple sessions exist.

    ``shutil.which`` is patched so the count check is reached on a machine
    without omp installed (CI) instead of failing on the PATH guard first.
    """
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/omp")
    trial_dir = tmp_path / "trial"
    (trial_dir / "agent" / "omp-sessions").mkdir(parents=True)

    # Zero sessions
    with pytest.raises(ValueError, match="Expected exactly 1"):
        OmpAgent.handoff(trial_dir, tmp_path)

    # Two sessions
    (trial_dir / "agent" / "omp-sessions" / "s1.jsonl").write_text("{}", encoding="utf-8")
    (trial_dir / "agent" / "omp-sessions" / "s2.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected exactly 1"):
        OmpAgent.handoff(trial_dir, tmp_path)


def test_handoff_copies_session_and_returns_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """handoff copies the session into the local omp session dir and returns the
    resume argv.

    The local home is isolated on purpose: the first cut of this test copied
    into the developer's real ``~/.omp/sessions`` (DEFECTS, 2026-10-10).
    """
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/omp")
    monkeypatch.delenv("PI_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    trial_dir = tmp_path / "trial"
    session_dir = trial_dir / "agent" / "omp-sessions"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session-abc123.jsonl"
    session_file.write_text('{"type":"session","id":"s1"}\n', encoding="utf-8")

    result = OmpAgent.handoff(trial_dir, tmp_path)

    assert result == ["omp", "--resume", "session-abc123"]
    assert (tmp_path / ".omp" / "sessions" / "session-abc123.jsonl").is_file()


def test_handoff_finds_a_trial_with_a_custom_session_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """session_dir_name is configurable: a trial that overrode it still hands
    off, via the one-level fallback scan under agent/."""
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/omp")
    monkeypatch.delenv("PI_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    trial_dir = tmp_path / "trial"
    session_dir = trial_dir / "agent" / "custom-sessions"
    session_dir.mkdir(parents=True)
    (session_dir / "session-xyz.jsonl").write_text(
        '{"type":"session","id":"s1"}\n', encoding="utf-8"
    )

    result = OmpAgent.handoff(trial_dir, tmp_path)

    assert result == ["omp", "--resume", "session-xyz"]
    assert (tmp_path / ".omp" / "sessions" / "session-xyz.jsonl").is_file()
