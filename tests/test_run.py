"""The run: argv shape, the recorded identity, install-only, and the exit path.

Everything here is observed through the environment the agent drives: the
record it uploads, the command it runs, and the script it hands to the agent
user.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path, PurePosixPath

import pytest
from conftest import MODEL, RecordingEnvironment
from harbor.models.agent.context import AgentContext

from harbor_omp.omp_agent import RUN_FLAGS_RECORD


def test_the_run_flags_option_is_what_the_argv_carries(make_agent) -> None:
    """Profile-pinned flags reach the argv verbatim, and no flag the caller did
    not pass is added."""
    agent = make_agent(run_flags=["--no-extensions", "--no-skills", "--no-rules"])

    argv, model = agent._run_argv("do the task")

    assert argv[:4] == ["omp", "-p", "--auto-approve", "--no-extensions"]
    assert "--no-skills" in argv
    assert "--no-rules" in argv
    assert "--no-lsp" not in argv
    assert f"--model={model}" in argv
    assert model == MODEL


def test_no_run_flags_turns_every_optional_extension_off(make_agent) -> None:
    """The default recipe: omp runs with no extensions, skills, rules or LSP,
    which is what keeps a trial's tools the ones the caller pinned."""
    agent = make_agent()

    argv, _ = agent._run_argv("do the task")

    assert [flag for flag in argv if flag.startswith("--no-")] == [
        "--no-extensions",
        "--no-skills",
        "--no-rules",
        "--no-lsp",
    ]


def test_empty_run_flags_run_omp_with_its_own_defaults(make_agent) -> None:
    """``run_flags=[]`` is a real choice: no ``--no-*`` flag at all."""
    agent = make_agent(run_flags=[])

    argv, _ = agent._run_argv("do the task")

    assert [flag for flag in argv if flag.startswith("--no-")] == []
    assert argv[3].startswith("--session-dir=")


def test_a_model_without_a_provider_is_refused(make_agent) -> None:
    """Harbor's provider/model convention is enforced here, so the failure is
    named, not a mysterious omp error."""
    agent = make_agent(model_name="deepseek-v4-flash")

    with pytest.raises(ValueError, match="provider/model"):
        agent._run_argv("do the task")


def test_install_only_records_the_argv_and_runs_nothing(make_agent) -> None:
    """The zero-spend gate with no pre-commands: the exact argv lands in the
    record, and no command runs at all."""
    env = RecordingEnvironment()
    agent = make_agent(install_only=True)

    asyncio.run(agent.run("do the task", env, AgentContext()))

    assert env.execs == []
    record = json.loads(env.uploaded[RUN_FLAGS_RECORD.as_posix()])
    assert record["model"] == MODEL
    assert record["argv"][-1] == "do the task"
    assert "--no-lsp" in record["argv"]


def test_install_only_runs_pre_commands_and_never_the_agent(make_agent) -> None:
    """Install-time evidence is what an install-only trial exists to capture:
    the pre-commands run in the agent's own shell (same prologue), while the
    agent never launches and the post-commands never run."""
    env = RecordingEnvironment()
    agent = make_agent(
        install_only=True,
        pre_commands=["echo evidence > /logs/agent/pre-ran.txt"],
        post_commands=["echo collected"],
    )

    asyncio.run(agent.run("do the task", env, AgentContext()))

    pre = env.commands_matching("pre-ran.txt")
    assert len(pre) == 1
    # The shared prologue means the pre-command sees the isolated config home
    # the agent would have run under.
    assert "export HOME=/tmp/omp-home PI_CONFIG_DIR=.omp" in pre[0]
    assert env.commands_matching("echo collected") == []
    assert env.commands_matching("omp -p") == []
    # The argv is still recorded: an install-only trial always shows what it
    # would have run.
    assert RUN_FLAGS_RECORD.as_posix() in env.uploaded


def test_a_normal_run_records_the_argv_before_launching_omp(make_agent) -> None:
    """The record is the identity of what ran; it must exist even if omp never
    finishes."""
    env = RecordingEnvironment()
    agent = make_agent()

    asyncio.run(agent.run("do the task", env, AgentContext()))

    record_upload = env.index_of_first("upload", RUN_FLAGS_RECORD.as_posix())
    launch = env.index_of_first("exec", "omp -p")
    assert record_upload < launch
    record = json.loads(env.uploaded[RUN_FLAGS_RECORD.as_posix()])
    assert record["argv"][-1] == "do the task"


def test_the_agent_output_is_captured_and_its_status_reported(make_agent) -> None:
    """Output is tee'd to omp.txt under the log dir, and the script exits with
    the agent's status, which is what Harbor classifies."""
    env = RecordingEnvironment()
    agent = make_agent()

    asyncio.run(agent.run("do the task", env, AgentContext()))

    script = env.commands_matching("omp -p")[0]
    assert "| tee /logs/agent/omp.txt" in script
    assert "rc=${PIPESTATUS[0]}" in script
    assert "exit $harbor_omp_agent_rc" in script


def test_the_agent_runs_under_the_isolated_config_home(make_agent) -> None:
    """HOME and PI_CONFIG_DIR are the isolated pair the config steps wrote to,
    and PATH still reaches the bun install from the original home."""
    env = RecordingEnvironment()
    agent = make_agent(config_home="/tmp/trial-home")

    asyncio.run(agent.run("do the task", env, AgentContext()))

    script = env.commands_matching("omp -p")[0]
    assert "export HOME=/tmp/trial-home PI_CONFIG_DIR=.omp" in script
    assert 'ORIG_HOME="$HOME"' in script
    assert 'export PATH="$ORIG_HOME/.bun/bin:$PATH"' in script


def test_remote_session_logs_dir_follows_the_session_dir_name(make_agent) -> None:
    """The session dir Harbor syncs for live previews is the dir omp writes."""
    agent = make_agent(session_dir_name="sessions-here")

    assert agent.remote_session_logs_dir == PurePosixPath("/logs/agent/sessions-here")


def test_the_session_dir_name_moves_the_flag_the_dir_and_the_reader(make_agent) -> None:
    """One option, one directory: --session-dir, remote_session_logs_dir and the
    post-run read all follow it."""
    agent = make_agent(session_dir_name="my-sessions")

    argv, _ = agent._run_argv("do the task")

    assert "--session-dir=/logs/agent/my-sessions" in argv
    assert agent.remote_session_logs_dir == PurePosixPath("/logs/agent/my-sessions")


def test_extra_files_are_uploaded_with_their_contents(make_agent, tmp_path: Path) -> None:
    """The upload hook ships the caller's files to the caller's targets."""
    collector = tmp_path / "collector.py"
    collector.write_bytes(b"print('collector')\n")
    shim = tmp_path / "gh_shim.py"
    shim.write_bytes(b"print('shim')\n")
    env = RecordingEnvironment()
    agent = make_agent(
        extra_files=[
            (str(collector), "/tmp/harbor-collector/collector.py"),
            (str(shim), "/tmp/harbor-collector/gh_shim.py"),
        ]
    )

    asyncio.run(agent.install(env))

    assert env.uploaded["/tmp/harbor-collector/collector.py"] == b"print('collector')\n"
    assert env.uploaded["/tmp/harbor-collector/gh_shim.py"] == b"print('shim')\n"


def test_a_missing_extra_file_aborts_the_setup(make_agent, tmp_path: Path) -> None:
    """A hook that silently received nothing is worse than a failed setup."""
    env = RecordingEnvironment()
    agent = make_agent(extra_files=[(str(tmp_path / "absent.py"), "/tmp/absent.py")])

    with pytest.raises(ValueError, match="not a readable file"):
        asyncio.run(agent.install(env))

    assert env.uploads == []


def test_the_install_proves_the_system_dependencies_it_needs(make_agent) -> None:
    """bun's installer needs unzip, and the shipping steps need git and curl:
    the install asks for all three instead of assuming them."""
    env = RecordingEnvironment()

    asyncio.run(make_agent().install(env))

    checks = " ".join(env.commands)
    for dependency in ("curl", "git", "unzip"):
        assert f"command -v {dependency}" in checks


def test_the_install_creates_the_dirs_the_run_writes_to(make_agent) -> None:
    """The session dir and the resolved dir exist before anything writes them."""
    env = RecordingEnvironment()

    asyncio.run(make_agent(session_dir_name="my-sessions").install(env))

    install = env.commands_matching("bun install -g")[0]
    assert "mkdir -p /logs/agent/my-sessions /logs/agent/resolved" in install
    assert "omp --version" in install


def test_a_prompt_template_is_applied_to_the_instruction(make_agent, tmp_path: Path) -> None:
    """Harbor's declared prompt-template option is not inert for this agent:
    the rendered instruction is what the argv carries."""
    template = tmp_path / "prompt.j2"
    template.write_text("wrapped: {{ instruction }}", encoding="utf-8")
    env = RecordingEnvironment()
    agent = make_agent(prompt_template_path=str(template))

    asyncio.run(agent.run("do the task", env, AgentContext()))

    record = json.loads(env.uploaded[RUN_FLAGS_RECORD.as_posix()])
    assert record["argv"][-1] == "wrapped: do the task"
