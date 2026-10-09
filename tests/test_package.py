"""What the package declares to Harbor, checked against what it does.

Harbor gates a job on the declared capabilities before any spend, so a flag that
is true without the behaviour behind it is worse than a missing feature: the gate
would pass and the trial would silently produce nothing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath

import pytest
from conftest import RecordingEnvironment
from harbor.agents.installed.base import BaseInstalledAgent
from harbor.models.agent.context import AgentContext

from harbor_omp import OmpAgent


def test_the_agent_identity_is_the_short_product_name() -> None:
    """Harbor's agent ids are short product names, and this one is what every
    trial record shows, so it is asserted rather than assumed."""
    assert OmpAgent.name() == "omp"


def test_the_adapter_is_an_installed_agent() -> None:
    """omp runs inside the task environment; Harbor's installed-agent machinery
    (setup, version detection, error classification) is what wraps it."""
    assert issubclass(OmpAgent, BaseInstalledAgent)


def test_atif_is_claimed_and_a_trajectory_really_is_produced(make_agent, tmp_path: Path) -> None:
    """``capabilities.atif`` is true because the converter produces one — the
    flag is a promise Harbor gates on, so the declaration is checked against the
    behaviour. An empty logs dir is still *absent*: no session, no trajectory."""
    agent = make_agent()

    assert agent.capabilities.atif is True
    assert agent.convert_trajectory(tmp_path) is None

    directory = tmp_path / "omp-sessions"
    directory.mkdir()
    (directory / "session.jsonl").write_text(
        '{"type":"session","id":"s","timestamp":"2026-10-09T12:00:00.000Z"}\n'
        '{"type":"message","timestamp":"2026-10-09T12:00:01.000Z","message":'
        '{"role":"user","content":[{"type":"text","text":"do it"}]}}\n',
        encoding="utf-8",
    )

    built = agent.convert_trajectory(tmp_path)

    assert built is not None
    assert [step.source for step in built.steps] == ["system", "user"]
    assert built.agent.name == "omp"


def test_resume_load_and_handoff_are_refused_not_faked(make_agent, tmp_path: Path) -> None:
    """Declared false and refused at runtime: a job that asks for them fails
    loudly instead of producing a run with no session to continue."""
    agent = make_agent()

    assert agent.capabilities.resume is False
    assert agent.capabilities.load_native_trajectory is False
    assert agent.capabilities.load_atif_trajectory is False
    assert agent.capabilities.handoff is False

    environment = RecordingEnvironment()
    with pytest.raises(NotImplementedError):
        asyncio.run(agent.resume("do the task", environment, AgentContext()))
    with pytest.raises(NotImplementedError):
        asyncio.run(agent.load("do the task", environment, AgentContext()))
    with pytest.raises(NotImplementedError):
        agent.handoff(tmp_path, tmp_path)


def test_skills_and_mcp_are_not_claimed(make_agent) -> None:
    """Both seams are unimplemented (skills travel as config content instead),
    so Harbor must refuse a task that configures them rather than ignoring it."""
    capabilities = make_agent().capabilities

    assert capabilities.skills is False
    assert capabilities.mcp_servers is False
    assert capabilities.native_config is False


def test_the_option_model_is_the_declared_one() -> None:
    """Harbor compiles ``--agent-kwarg`` through this model; if it stopped being
    the adapter's model, every documented option would become a silent no-op."""
    assert OmpAgent.options_model is not None
    assert OmpAgent.options_model.__name__ == "OmpOptions"


def test_the_package_exports_the_documented_names() -> None:
    """The import path in the README is the API: ``harbor_omp:OmpAgent``."""
    import harbor_omp

    assert "OmpAgent" in harbor_omp.__all__
    assert harbor_omp.OmpAgent.name() == "omp"


def test_the_session_dir_lives_under_harbors_mounted_log_dir(make_agent) -> None:
    """Harbor mounts /logs/agent; the session dir must be inside it, or the
    metrics would have to be copied off the container by hand."""
    agent = make_agent(environment_logs_dir=PurePosixPath("/logs/agent"))

    directory = agent.remote_session_logs_dir

    assert directory is not None
    assert directory.is_relative_to(PurePosixPath("/logs/agent"))
