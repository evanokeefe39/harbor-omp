"""The extension points, executed.

The generated run script is run for real, with a POSIX shell and a stubbed
``omp``/``bun`` on PATH, because the two properties that matter are shell
properties: a pre-command's export must reach the agent, and a post-command
must never change the agent's status.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath

import pytest

from harbor_omp import OmpAgent

MODEL = "openrouter/deepseek/deepseek-v4-flash"


def _posix_shell() -> str:
    """A shell that can run the adapter's run script.

    On Windows the PATH ``bash`` is usually WSL's, which cannot see the Windows
    temp paths a test uses; Git Bash can, and is where it normally lives.
    """

    if os.name == "nt":
        programs = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        git_bash = programs / "Git" / "bin" / "bash.exe"
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    assert found, "the hook tests need a POSIX shell (bash)"
    return found


def _hook_agent(logs_dir: Path, **options: object) -> OmpAgent:
    """An agent whose log dir is a POSIX path the test shell can write to."""

    arguments: dict[str, object] = {
        "logs_dir": logs_dir,
        "model_name": MODEL,
        "environment_logs_dir": PurePosixPath(
            f"/tmp/harbor-omp-hook-{uuid.uuid4().hex[:10]}"
        ),
    }
    arguments.update(options)
    return OmpAgent(**arguments)


def run_script(
    agent: OmpAgent, instruction: str = "do the task", omp_body: str = "return 0"
) -> subprocess.CompletedProcess[str]:
    """Run the adapter's real run script with the agent CLI stubbed out."""

    argv, _ = agent._run_argv(instruction)
    # The stub body goes on its own line: bash needs a terminator before `}`.
    program = f"omp() {{\n{omp_body}\n}}\nbun() {{\n:\n}}\n{agent._run_command(argv)}\n"
    env = dict(os.environ)
    env["PATH"] = "/usr/bin:/bin"
    env["HOME"] = "/tmp"
    return subprocess.run(
        [_posix_shell(), "-c", program],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_a_pre_command_export_reaches_the_agent(tmp_path: Path) -> None:
    """The pre-commands run in the agent's own shell, which is the only way a
    harness can give the agent extra environment variables."""
    agent = _hook_agent(tmp_path, pre_commands=["export HOOK_PROBE=from-pre"])

    result = run_script(agent, omp_body='echo "AGENT-PROBE=${HOOK_PROBE-unset}"')

    assert result.returncode == 0
    assert "AGENT-PROBE=from-pre" in result.stdout


def test_a_failing_pre_command_aborts_before_the_agent(tmp_path: Path) -> None:
    """The pre-spend gate: an environment that fails its own check never gets
    to spend model tokens, and the failure is named with its status."""
    agent = _hook_agent(tmp_path, pre_commands=["false"])

    result = run_script(agent, omp_body='echo "AGENT-RAN"')

    assert result.returncode == 1
    assert "AGENT-RAN" not in result.stdout
    assert "pre-command failed" in result.stderr


def test_the_agents_status_is_what_the_run_reports(tmp_path: Path) -> None:
    """Harbor classifies the agent's own exit code."""
    result = run_script(_hook_agent(tmp_path), omp_body="return 5")

    assert result.returncode == 5


def test_a_failing_post_command_never_changes_the_agents_status(tmp_path: Path) -> None:
    """Collection is best-effort: it is loud on stderr and silent on the exit
    code, so a failing collector cannot hide a failing agent or fail a good one."""
    agent = _hook_agent(tmp_path, post_commands=["false"])

    result = run_script(agent, omp_body="echo AGENT-RAN; return 3")

    assert result.returncode == 3
    assert "AGENT-RAN" in result.stdout
    assert "post-command failed" in result.stderr


def test_a_post_command_cannot_steal_the_exit_code(tmp_path: Path) -> None:
    """Even a post-command that writes the adapter's own variable names cannot
    change the status the run reports."""
    agent = _hook_agent(tmp_path, post_commands=["rc=7"])

    result = run_script(agent, omp_body="return 0")

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("agent_rc", "post_command"),
    [
        # A green agent must stay green even when the post side exits non-zero.
        (0, "exit 7"),
        # A failing agent must report its own status, not the post side's 0:
        # this is the shape that used to turn a red trial green, so Harbor's
        # error classifier never saw the failure.
        (3, "exit 0"),
        (5, "trap 'exit 0' EXIT"),
    ],
)
def test_a_post_command_cannot_replace_the_agents_status(
    tmp_path: Path, agent_rc: int, post_command: str
) -> None:
    """A post-command that exits, or that traps EXIT, used to end the run with
    its own status; the block is contained, so the agent's status is what the
    run reports."""
    agent = _hook_agent(tmp_path, post_commands=[post_command])

    result = run_script(agent, omp_body=f"echo AGENT-RAN; return {agent_rc}")

    assert "AGENT-RAN" in result.stdout
    assert result.returncode == agent_rc


def test_errexit_in_a_post_command_cannot_kill_the_run(tmp_path: Path) -> None:
    """``set -e`` used to end the whole script at the first failing
    post-command, before the hook's own status was recorded: the failure line
    never printed and a green agent was reported as a failed run."""
    agent = _hook_agent(tmp_path, post_commands=["set -e", "false"])

    result = run_script(agent, omp_body="echo AGENT-RAN; return 0")

    assert result.returncode == 0
    assert "post-command failed" in result.stderr


def test_pre_commands_and_post_commands_run_in_order(tmp_path: Path) -> None:
    """Before the agent, then the agent, then after it — the collector pattern
    depends on the post side really being after."""
    agent = _hook_agent(
        tmp_path,
        pre_commands=["echo FIRST", "echo SECOND"],
        post_commands=["echo LAST"],
    )

    result = run_script(agent, omp_body="echo AGENT")

    order = [token for token in ("FIRST", "SECOND", "AGENT", "LAST") if token in result.stdout]
    assert order == ["FIRST", "SECOND", "AGENT", "LAST"]


def test_the_agent_sees_the_isolated_home_and_config_dir(tmp_path: Path) -> None:
    """The documented isolation is what the agent process actually gets."""
    agent = _hook_agent(tmp_path, config_home="/tmp/hook-home")

    result = run_script(agent, omp_body='echo "HOME=$HOME CONFIG=$PI_CONFIG_DIR"')

    assert "HOME=/tmp/hook-home CONFIG=.omp" in result.stdout


def test_the_workspace_is_the_shared_working_directory(tmp_path: Path) -> None:
    """Hooks and the agent run from the same cwd, so a caller's relative paths
    mean the same thing on both sides of the agent."""
    agent = _hook_agent(tmp_path, pre_commands=["echo PRE-CWD=$(pwd)"])

    result = run_script(agent, omp_body='echo "AGENT-CWD=$(pwd)"')

    # /app does not exist on a test host, so both report the fallback cwd — the
    # point is that they agree.
    pre = next(line for line in result.stdout.splitlines() if line.startswith("PRE-CWD="))
    agent_cwd = next(
        line for line in result.stdout.splitlines() if line.startswith("AGENT-CWD=")
    )
    assert pre.split("=", 1)[1] == agent_cwd.split("=", 1)[1]


@pytest.mark.parametrize("where", ["pre", "post"])
def test_commands_that_touch_the_session_dir_are_not_swallowed(
    tmp_path: Path, where: str
) -> None:
    """A hook's own output is visible: the failure lines are the only thing the
    adapter adds."""
    agent = _hook_agent(tmp_path, **{f"{where}_commands": ['echo "HOOK-OUTPUT"']})

    result = run_script(agent)

    assert "HOOK-OUTPUT" in result.stdout
