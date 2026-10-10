"""The no-op guard, executed: a run that never acted must fail, not score.

On 2026-10-09, 22 of 30 fast-30 trials ended with omp exiting 0 after one
assistant message and no tool call — the model answered omp's system prompt
("Ready. What are we building?") instead of the task. Harbor scored each one
``reward 0``, indistinguishable from a real attempt (docs/worked-example.md § 3).

These tests drive ``OmpAgent.run`` against a real POSIX shell. A stubbed ``omp``
writes a session in omp's own on-disk encoding (compact JSON lines) and exits
with a chosen status, so what is asserted is what Harbor would see: whether
``run`` raises the agent-failure error Harbor records on the trial.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath

import pytest
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.environments.base import ExecResult
from harbor.models.agent.context import AgentContext

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
    assert found, "the no-op guard tests need a POSIX shell (bash)"
    return found


def _line(event: dict[str, object]) -> str:
    """One session line, encoded the way omp writes it: compact JSON."""

    return json.dumps(event, separators=(",", ":"))


USER_TASK = _line(
    {
        "type": "message",
        "message": {"role": "user", "content": [{"type": "text", "text": "Build the model."}]},
    }
)

#: The recorded failure shape: one assistant message, text only, stop.
GREETING = _line(
    {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "The user's message is the system prompt?"},
                {"type": "text", "text": "Ready. What are we building or fixing?"},
            ],
            "stopReason": "stop",
        },
    }
)

#: A working first turn: the model acts on the task through a tool.
TOOL_TURN = _line(
    {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me inspect the project."},
                {
                    "type": "toolCall",
                    "id": "call_1",
                    "name": "bash",
                    "arguments": {"command": "ls"},
                },
            ],
            "stopReason": "toolUse",
        },
    }
)

#: A reply that *talks about* a tool call: the marker only appears escaped,
#: inside a string value, so it is not a tool call.
QUOTED_MARKER = _line(
    {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": 'omp logs a call as "type":"toolCall".'}],
            "stopReason": "stop",
        },
    }
)


class ShellEnvironment:
    """A ``BaseEnvironment`` stand-in that runs every exec in a real shell.

    ``omp`` and ``bun`` are shell functions: the ``omp`` stub writes the given
    session lines into the ``--session-dir`` it was handed, then returns
    ``status`` — the two things the real CLI does that the guard reads.
    """

    def __init__(self, session_lines: list[str], status: int = 0) -> None:
        # The lines are printf *arguments*, never its format: a format string
        # would decode the JSON's own escapes (\" -> ") and write a session omp
        # never would.
        session = " ".join(shlex.quote(line) for line in session_lines)
        self.prelude = (
            "omp() {\n"
            '  for arg in "$@"; do case "$arg" in --session-dir=*) dir="${arg#--session-dir=}";; esac; done\n'
            '  mkdir -p "$dir"\n'
            f"  printf '%s\\n' {session} > \"$dir/session.jsonl\"\n"
            f"  return {status}\n"
            "}\n"
            "bun() {\n:\n}\n"
        )
        self.commands: list[str] = []

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        return None

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        self.commands.append(command)
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


def _agent(logs_dir: Path) -> OmpAgent:
    return OmpAgent(
        logs_dir=logs_dir,
        model_name=MODEL,
        environment_logs_dir=PurePosixPath(f"/tmp/harbor-omp-noop-{uuid.uuid4().hex[:10]}"),
    )


def _run(agent: OmpAgent, env: ShellEnvironment) -> None:
    asyncio.run(agent.run("Build the model.", env, AgentContext()))  # type: ignore[arg-type]


def test_a_run_that_never_called_a_tool_fails_instead_of_scoring(tmp_path: Path) -> None:
    """The recorded defect: omp exits 0 after a greeting. Harbor must see an
    agent failure, not a finished run the verifier will score 0."""
    env = ShellEnvironment([USER_TASK, GREETING], status=0)

    with pytest.raises(NonZeroAgentExitCodeError, match="no tool call"):
        _run(_agent(tmp_path), env)


def test_a_tool_call_quoted_in_text_is_not_a_tool_call(tmp_path: Path) -> None:
    """The guard reads structure, not prose: a reply that merely mentions the
    marker has still not acted on the task."""
    env = ShellEnvironment([USER_TASK, QUOTED_MARKER], status=0)

    with pytest.raises(NonZeroAgentExitCodeError, match="no tool call"):
        _run(_agent(tmp_path), env)


def test_a_run_that_acted_through_a_tool_finishes_normally(tmp_path: Path) -> None:
    """A real attempt — even a short one — passes the guard untouched."""
    env = ShellEnvironment([USER_TASK, TOOL_TURN, GREETING], status=0)

    _run(_agent(tmp_path), env)


def test_a_failing_agent_is_reported_as_its_own_failure(tmp_path: Path) -> None:
    """omp's own non-zero status is what Harbor classifies; the guard does not
    run after a failed agent and does not relabel its failure."""
    env = ShellEnvironment([USER_TASK, GREETING], status=5)

    with pytest.raises(NonZeroAgentExitCodeError) as raised:
        _run(_agent(tmp_path), env)

    assert "exit 5" in str(raised.value)
    assert "no tool call" not in str(raised.value)
