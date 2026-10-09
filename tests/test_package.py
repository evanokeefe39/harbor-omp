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


def test_no_atif_is_claimed_and_none_is_produced(make_agent, tmp_path: Path) -> None:
    """``capabilities.atif`` is false, and the converter really produces nothing
    (the default base-class behaviour)."""
    agent = make_agent()

    assert agent.capabilities.atif is False
    assert agent.convert_trajectory(tmp_path) is None


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
