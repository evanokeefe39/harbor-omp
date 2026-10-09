"""The option surface: what a caller sets, and what it reaches."""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath

import pytest
from conftest import RecordingEnvironment

from harbor_omp import OmpOptions
from harbor_omp.install import install_command
from harbor_omp.options import OMP_PACKAGE, PINNED_OMP_VERSION, package_spec


def test_the_version_option_is_what_the_install_installs(make_agent) -> None:
    """A pinned version reaches the install command verbatim, and the pin this
    package was built around is not installed behind the caller's back."""
    agent = make_agent(version="@oh-my-pi/pi-coding-agent@9.9.9")
    env = RecordingEnvironment()

    asyncio.run(agent.install(env))

    installs = env.commands_matching("bun install -g")
    assert len(installs) == 1
    assert "--ignore-scripts @oh-my-pi/pi-coding-agent@9.9.9" in installs[0]
    assert PINNED_OMP_VERSION not in installs[0]


def test_a_bare_version_is_read_as_the_omp_package(make_agent) -> None:
    """``--agent-kwarg version=18.6.1`` installs omp at 18.6.1, not a package
    literally named 18.6.1."""
    agent = make_agent(version="18.6.1")
    env = RecordingEnvironment()

    asyncio.run(agent.install(env))

    install = env.commands_matching("bun install -g")[0]
    assert f"--ignore-scripts {OMP_PACKAGE}@18.6.1" in install


def test_a_blank_version_is_refused_before_anything_is_installed(make_agent) -> None:
    """An install that cannot name its package must not silently install
    whatever the registry resolves."""
    agent = make_agent(version="  ")
    env = RecordingEnvironment()

    with pytest.raises(ValueError, match="blank"):
        asyncio.run(agent.install(env))

    assert env.execs == []
    assert env.uploads == []


def test_package_spec_passes_scoped_and_namespaced_specs_through() -> None:
    """A scoped spec is already a spec; a fork's spec is left alone."""
    assert package_spec("@oh-my-pi/pi-coding-agent@18.6.0") == PINNED_OMP_VERSION
    assert package_spec("@acme/omp-fork") == "@acme/omp-fork"
    assert package_spec("18.6.0") == PINNED_OMP_VERSION
    assert package_spec("omp-fork") == f"{OMP_PACKAGE}@omp-fork"


def test_a_version_with_a_shell_metacharacter_stays_one_argument(make_agent) -> None:
    """The install command is shell text: a spec with a space or a ``;`` must
    reach bun as one argument instead of splicing extra commands into the
    install."""
    agent = make_agent(version="@oh-my-pi/pi-coding-agent@18.6.1; echo injected")
    env = RecordingEnvironment()

    asyncio.run(agent.install(env))

    install = env.commands_matching("bun install -g")[0]
    assert "--ignore-scripts '@oh-my-pi/pi-coding-agent@18.6.1; echo injected'" in install
    assert "mkdir -p /logs/agent/omp-sessions /logs/agent/resolved" in install


def test_the_install_command_quotes_the_directories_it_creates() -> None:
    """``install_command`` is public, so a caller's own directory is quoted
    too: a path with a space must not split into two arguments."""
    command = install_command(
        PINNED_OMP_VERSION,
        directories=(PurePosixPath("/logs/agent/my sessions"),),
    )

    assert "mkdir -p '/logs/agent/my sessions'" in command


def test_the_thinking_option_answers_to_reasoning_effort_too(make_agent) -> None:
    """Both names are the same knob: a caller with a reasoning-effort habit is
    not silently ignored."""
    assert OmpOptions.model_validate({"reasoning_effort": "high"}).thinking == "high"
    assert OmpOptions.model_validate({"thinking": "low"}).thinking == "low"
    agent = make_agent(thinking="medium")

    argv, _ = agent._run_argv("do the task")

    assert "--thinking=medium" in argv


def test_options_from_the_harness_this_came_from_are_refused(make_agent) -> None:
    """Harness-only knobs — benchmark, web access, gh scripts, the old
    omp_config/router_plugin shapes — are not options here, and any typo in an
    agent kwarg is an error rather than a silent no-op."""
    leftovers = (
        "benchmark",
        "web_access",
        "gh_scripted_responses",
        "omp_config",
        "router_plugin",
    )
    for leftover in leftovers:
        with pytest.raises(ValueError, match=leftover):
            make_agent(**{leftover: "anything"})


def test_a_plugin_without_run_flags_is_refused(make_agent) -> None:
    """The default flags include ``--no-extensions``, which also gates plugin
    loading: a caller who ships a plugin without saying how omp should run gets
    a plugin that never loads, so the combination is refused instead of
    installed silently."""
    with pytest.raises(ValueError, match="run_flags"):
        make_agent(plugin={"name": "demo-plugin", "src": "/tmp/plugin-src"})


def test_a_plugin_with_explicit_run_flags_is_accepted(make_agent) -> None:
    """The way to ship a plugin is to say so: explicit flags are the caller's
    decision about what omp loads, and they reach the argv."""
    agent = make_agent(
        plugin={"name": "demo-plugin", "src": "/tmp/plugin-src"}, run_flags=[]
    )

    argv, _ = agent._run_argv("do the task")

    assert [flag for flag in argv if flag.startswith("--no-")] == []


@pytest.mark.parametrize(
    "value",
    ["", "   ", " /", "a/b", "a\\b", "..", ".", "two words", "trailing "],
)
def test_a_session_dir_name_that_is_not_one_path_segment_is_refused(
    make_agent, value: str
) -> None:
    """The name is spliced into container paths and shell commands, so it must
    be one path segment: anything else would silently write outside the log
    dir or split into two arguments."""
    with pytest.raises(ValueError, match="session_dir_name"):
        make_agent(session_dir_name=value)


def test_a_plain_session_dir_name_is_accepted(make_agent) -> None:
    """The refusal must not cost the normal case."""
    agent = make_agent(session_dir_name="omp-sessions-2")

    argv, _ = agent._run_argv("do the task")

    assert "--session-dir=/logs/agent/omp-sessions-2" in argv
